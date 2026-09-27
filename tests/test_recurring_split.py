""""עדכן להבא" מפצל את הסדרה — ולא כותב מחדש את החודש הראשון.

עד היום "עדכן להבא" עדכן את שורת התבנית, והתבנית היא גם העסקה של
החודש הראשון. שכר דירה מינואר ב-5,000, שנערך בספטמבר ל-5,500, הפך גם
את ינואר ל-5,500.

הפיצול חי ב-SQL (‎split_recurring_series‎), אז הבדיקות כאן רצות מול המסד
האמיתי בתור משפחת הבדיקה — לא מול החשבון של אף אחד — ומנקות אחריהן.

הסדרה: חודשית ב-1 לחודש מינואר 2026. אפריל ואוגוסט דולגו (נמחקו בעבר),
כך שיש דילוג לפני נקודת הפיצול ודילוג אחריה. מפצלים ביוני — חודש שיש
אחריו מופעים שכבר נוצרו (יולי, ספטמבר), כי שם בדיוק כפילות הייתה נולדת.
"""
import uuid

import pytest

from backend import supabase_config as db

_MONTHS_WITH_INSTANCES = ["02", "03", "05", "06", "07", "09"]


def _table(name):
    return db.get_client().table(name)


@pytest.fixture
def series(family_a):
    db.set_auth_token(family_a["token"])
    fid = family_a["family_id"]
    marker = f"SPLIT-{uuid.uuid4().hex[:8]}"
    ids = {}
    try:
        template = _table("transactions").insert({
            "family_id": fid, "amount": 5000, "type": "expense",
            "date": "2026-01-01", "description": marker,
            "is_recurring": True, "recurring_frequency": "monthly_1",
            "recurring_skips": ["2026-04-01", "2026-08-01"],
        }).execute().data[0]
        ids["template"] = template["id"]
        for mm in _MONTHS_WITH_INSTANCES:
            row = _table("transactions").insert({
                "family_id": fid, "amount": 5000, "type": "expense",
                "date": f"2026-{mm}-01", "description": marker,
                "is_recurring": False, "recurring_parent_id": template["id"],
                "recurring_frequency": "monthly_1",
            }).execute().data[0]
            ids[mm] = row["id"]
        yield {"fid": fid, "marker": marker, "ids": ids, "family": family_a}
    finally:
        db.set_auth_token(family_a["token"])
        _table("transactions").delete().eq("family_id", fid).eq("description", marker).execute()


def _rows(s):
    db.set_auth_token(s["family"]["token"])
    rows = _table("transactions").select("*").eq("family_id", s["fid"]) \
        .eq("description", s["marker"]).execute().data
    return {r["date"][5:7]: r for r in rows}


def _edit_june_and_split(s):
    """מה שהדפדפן עושה: קודם שומר את יוני בסכום החדש, ואז "עדכן להבא"."""
    db.set_auth_token(s["family"]["token"])
    _table("transactions").update({"amount": 5500}).eq("id", s["ids"]["06"]).execute()
    return db.split_recurring_series(s["ids"]["template"], s["ids"]["06"], s["fid"])


def test_the_first_month_is_not_rewritten(series):
    """הבאג עצמו."""
    new_id, err = _edit_june_and_split(series)

    assert err is None and new_id == series["ids"]["06"]
    rows = _rows(series)
    assert float(rows["01"]["amount"]) == 5000, "ינואר נכתב מחדש"


def test_the_old_series_ends_the_day_before(series):
    _edit_june_and_split(series)
    old = _rows(series)["01"]

    assert old["is_recurring"] is True
    assert old["recurring_end_date"] == "2026-05-31"
    assert old["recurring_skips"] == ["2026-04-01"], "דילוג שאחרי הפיצול נשאר בסדרה הישנה"


def test_the_edited_month_starts_the_new_series(series):
    _edit_june_and_split(series)
    june = _rows(series)["06"]

    assert june["is_recurring"] is True
    assert june["recurring_parent_id"] is None
    assert june["recurring_frequency"] == "monthly_1"
    assert june["recurring_end_date"] is None
    assert float(june["amount"]) == 5500
    assert june["recurring_skips"] == ["2026-08-01"], "הדילוג של אוגוסט לא עבר לסדרה החדשה"


def test_history_keeps_its_amounts_and_its_series(series):
    """מה שקדם לפיצול שייך לישנה; מה שאחריו עבר לחדשה — בלי שהסכום שלו השתנה."""
    _edit_june_and_split(series)
    rows = _rows(series)
    template, june = series["ids"]["template"], series["ids"]["06"]

    for mm in ("02", "03", "05"):
        assert rows[mm]["recurring_parent_id"] == template, f"{mm} עזב את הסדרה הישנה"
    for mm in ("07", "09"):
        assert rows[mm]["recurring_parent_id"] == june, f"{mm} לא עבר לסדרה החדשה"
        assert float(rows[mm]["amount"]) == 5000, f"{mm} נכתב מחדש"


def test_the_engine_creates_no_duplicates_afterwards(series):
    """הסיבה שהמופעים המאוחרים חייבים לעבור: סדרה חדשה שלא רואה את יולי
    ואת ספטמבר הייתה יוצרת אותם שוב. והישנה, שנגמרת במאי, לא אמורה ליצור
    כלום — אפריל דולג."""
    _edit_june_and_split(series)
    before = len(_rows(series))

    db.set_auth_token(series["family"]["token"])
    _, ok = db.materialize_recurring(series["fid"])

    assert ok
    rows = _table("transactions").select("date").eq("family_id", series["fid"]) \
        .eq("description", series["marker"]).execute().data
    assert len(rows) == before, sorted(r["date"] for r in rows)


def test_another_family_cannot_split(series, family_b):
    """הפונקציה עוקפת RLS; הבדיקה שבתוכה היא ההגנה היחידה."""
    db.set_auth_token(family_b["token"])
    new_id, err = db.split_recurring_series(
        series["ids"]["template"], series["ids"]["06"], series["fid"])

    assert (new_id, err) == (None, None)
    assert _rows(series)["06"]["is_recurring"] is False, "משפחה אחרת פיצלה"


def test_an_instance_of_a_different_series_is_refused(series):
    """ה-UI שולח את שני המזהים; שילוב שלא מתאים אסור שיגע במשהו."""
    db.set_auth_token(series["family"]["token"])
    new_id, _ = db.split_recurring_series(
        series["ids"]["06"], series["ids"]["07"], series["fid"])

    assert new_id is None
    assert _rows(series)["01"]["recurring_end_date"] is None
