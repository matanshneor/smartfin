"""עריכת עסקה קבועה מ"עסקאות קבועות" בהגדרות — מהחודש הנוכחי והלאה (מתן, 2.10).

התבנית היא גם העסקה של החודש הראשון, ולכן עריכה שלה כתבה מחדש את ינואר:
שכר דירה מינואר ב-₪5,000 שנערך באוקטובר ל-₪5,500 הפך גם את ינואר ל-₪5,500,
ואוקטובר — שכבר נוצר — נשאר ₪5,000. עכשיו השינוי נכתב על המופע של החודש
והסדרה מתפצלת בו, כמו "עדכון להבא".

הפיצול חי ב-SQL, אז הבדיקות רצות מול המסד האמיתי בתור משפחת הבדיקה,
עם שעון קבוע, ומנקות אחריהן.
"""
import datetime
import uuid

import pytest

from backend import app as app_module
from backend import clock
from backend import supabase_config as db
from tests.conftest import category_of


def _table(name):
    return db.get_client().table(name)


def _freeze(monkeypatch, day):
    monkeypatch.setattr(clock, "today", lambda: day)
    monkeypatch.setattr(clock, "now", lambda: datetime.datetime(day.year, day.month, day.day, 12, 0))


@pytest.fixture
def make_series(family_a):
    """סדרה + המופעים שכבר "נוצרו". מחזירה פונקציה; מנקה בסוף."""
    db.set_auth_token(family_a["token"])
    fid = family_a["family_id"]
    marker = f"SEF-{uuid.uuid4().hex[:8]}"

    def build(start, freq, instance_dates):
        cat = category_of(fid)
        tpl = _table("transactions").insert({
            "family_id": fid, "amount": 5000, "type": "expense", "date": start,
            "description": marker, "category_id": cat, "is_recurring": True,
            "recurring_frequency": freq,
        }).execute().data[0]
        for d in instance_dates:
            _table("transactions").insert({
                "family_id": fid, "amount": 5000, "type": "expense", "date": d,
                "description": marker, "category_id": cat, "is_recurring": False,
                "recurring_parent_id": tpl["id"], "recurring_frequency": freq,
            }).execute()
        return tpl

    yield {"fid": fid, "marker": marker, "build": build}
    db.set_auth_token(family_a["token"])
    _table("transactions").delete().eq("family_id", fid).eq("description", marker).execute()
    _table("transactions").delete().eq("family_id", fid).eq("description", marker + "-חדש").execute()


def _payload(tpl, **changes):
    p = {"amount": 5500.0, "type": "expense", "date": tpl["date"], "description": tpl["description"],
         "category_id": tpl["category_id"], "user_id": None, "is_recurring": True,
         "recurring_frequency": tpl["recurring_frequency"], "recurring_end_date": None,
         "project_id": None, "project_category_id": None}
    p.update(changes)
    return p


def _rows(s):
    rows = _table("transactions").select("*").eq("family_id", s["fid"]) \
        .in_("description", [s["marker"], s["marker"] + "-חדש"]).order("date").execute().data
    return {r["date"]: r for r in rows}


def _edit(tpl, s, payload):
    with app_module.app.app_context():
        reply = app_module._edit_series_from_now(tpl["id"], s["fid"], payload)
        return None if reply is None else reply.get_json() if not isinstance(reply, tuple) \
            else reply[0].get_json()


def test_this_months_occurrence_takes_the_change_and_history_stays(make_series, monkeypatch):
    """הדוגמה של מתן: שכר דירה מינואר, נערך בספטמבר."""
    _freeze(monkeypatch, datetime.date(2026, 9, 20))
    s = make_series
    months = [f"2026-{m:02d}-01" for m in range(2, 10)]
    tpl = s["build"]("2026-01-01", "monthly_1", months)

    out = _edit(tpl, s, _payload(tpl, description=s["marker"] + "-חדש"))

    assert out["series_from"] == "2026-09-01"
    rows = _rows(s)
    assert float(rows["2026-01-01"]["amount"]) == 5000, "ינואר נכתב מחדש"
    assert rows["2026-01-01"]["description"] == s["marker"], "גם התיאור של ינואר"
    for d in months[:-1]:
        assert float(rows[d]["amount"]) == 5000, f"{d} השתנה"
    sep = rows["2026-09-01"]
    assert float(sep["amount"]) == 5500 and sep["description"] == s["marker"] + "-חדש"
    assert sep["is_recurring"] is True and sep["recurring_parent_id"] is None
    assert rows["2026-01-01"]["recurring_end_date"] == "2026-08-31"


def test_when_this_months_occurrence_is_still_ahead_it_starts_there(make_series, monkeypatch):
    """משכורת ב-20 לחודש, והיום ה-10: המופע של החודש נוצר עכשיו, עם הערכים
    החדשים, ומשם הסדרה החדשה."""
    _freeze(monkeypatch, datetime.date(2026, 9, 10))
    s = make_series
    tpl = s["build"]("2026-06-20", "monthly_same", ["2026-07-20", "2026-08-20"])

    out = _edit(tpl, s, _payload(tpl))

    assert out["series_from"] == "2026-09-20"
    rows = _rows(s)
    assert [float(rows[d]["amount"]) for d in ("2026-06-20", "2026-07-20", "2026-08-20")] == [5000] * 3
    assert float(rows["2026-09-20"]["amount"]) == 5500 and rows["2026-09-20"]["is_recurring"] is True
    assert rows["2026-06-20"]["recurring_end_date"] == "2026-09-19"
    # כשיגיע ה-20 המנוע לא יכפיל אותו
    _freeze(monkeypatch, datetime.date(2026, 9, 25))
    db.materialize_recurring(s["fid"])
    assert len([d for d in _rows(s) if d.startswith("2026-09")]) == 1


def test_a_changed_frequency_goes_to_the_new_series(make_series, monkeypatch):
    _freeze(monkeypatch, datetime.date(2026, 9, 20))
    s = make_series
    tpl = s["build"]("2026-07-01", "monthly_1", ["2026-08-01", "2026-09-01"])

    _edit(tpl, s, _payload(tpl, recurring_frequency="monthly_15"))

    rows = _rows(s)
    assert rows["2026-09-01"]["recurring_frequency"] == "monthly_15"
    assert rows["2026-07-01"]["recurring_frequency"] == "monthly_1"


def test_a_series_that_started_this_month_is_edited_as_before(make_series, monkeypatch):
    """אין עבר להגן עליו — עריכה רגילה של התבנית."""
    _freeze(monkeypatch, datetime.date(2026, 9, 20))
    s = make_series
    tpl = s["build"]("2026-09-01", "monthly_1", [])

    assert _edit(tpl, s, _payload(tpl)) is None


def test_an_end_date_before_this_month_is_refused(make_series, monkeypatch):
    _freeze(monkeypatch, datetime.date(2026, 9, 20))
    s = make_series
    tpl = s["build"]("2026-07-01", "monthly_1", ["2026-08-01", "2026-09-01"])

    out = _edit(tpl, s, _payload(tpl, recurring_end_date=datetime.date(2026, 8, 15)))

    assert "תאריך הסיום" in out["error"]
    assert float(_rows(s)["2026-09-01"]["amount"]) == 5000, "נכתב למרות הסירוב"
