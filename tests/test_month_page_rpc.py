"""‎get_month_page‎ חייבת להחזיר בדיוק את מה שחמש השליפות החזירו.

זו הבדיקה שמצדיקה את ההחלפה. בלעדיה "זה נראה אותו דבר" הוא כל מה שיש,
ועמוד החודש הוא מספרים — סטייה שקטה בו היא בדיוק סוג הכשל שהאפליקציה
הזאת כבר נכוותה ממנו (ראו ‎data_unavailable‎ ב-app.py).

רצה מול המסד האמיתי בתור משפחת הבדיקה, כמו ‎test_rls_isolation‎, ומנקה
אחריה ב-finally גם כשהיא נכשלת.
"""
import uuid

import pytest

from backend import supabase_config as db

YEAR, MONTH = 2031, 3


def _table(name):
    return db.get_client().table(name)


@pytest.fixture
def month_fixture(family_a):
    """חודש עם כל ארבעת הקישורים שהשליפה הישנה עשתה: קטגוריה, פרופיל,
    פרויקט וקטגוריית פרויקט — ועסקה בלי אף אחד מהם, כי ‎null‎ מול ‎{}‎
    הוא בדיוק ההבדל שהתבניות בודקות."""
    db.set_auth_token(family_a["token"])
    fid = family_a["family_id"]
    marker = f"MP-{uuid.uuid4().hex[:8]}"
    created = {"transactions": [], "categories": [], "project_categories": [], "projects": []}

    try:
        cat = _table("categories").insert({
            "family_id": fid, "name": f"{marker}-cat", "icon": "🧪",
            "type": "expense", "is_custom": True, "sort_order": 999,
        }).execute().data[0]
        created["categories"].append(cat["id"])

        proj = _table("projects").insert({
            "family_id": fid, "name": f"{marker}-proj", "icon": "🏗️",
            "owner_id": family_a["user_id"],
        }).execute().data[0]
        created["projects"].append(proj["id"])

        pcat = _table("project_categories").insert({
            "family_id": fid, "project_id": proj["id"],
            "name": f"{marker}-pcat", "icon": "🔩", "type": "expense",
        }).execute().data[0]
        created["project_categories"].append(pcat["id"])

        rows = [
            # קטגוריה + פרופיל
            {"family_id": fid, "amount": 120.5, "type": "expense", "date": f"{YEAR}-{MONTH:02d}-05",
             "description": f"{marker}-with-cat", "category_id": cat["id"],
             "user_id": family_a["user_id"]},
            # פרויקט + קטגוריית פרויקט
            {"family_id": fid, "amount": 300, "type": "expense", "date": f"{YEAR}-{MONTH:02d}-11",
             "description": f"{marker}-project", "project_id": proj["id"],
             "project_category_id": pcat["id"], "user_id": family_a["user_id"]},
            # בלי שום קישור — כל ארבעת השדות המקוננים אמורים לצאת null
            {"family_id": fid, "amount": 42, "type": "income", "date": f"{YEAR}-{MONTH:02d}-20",
             "description": f"{marker}-bare"},
            # אותו תאריך כמו הקודמת: כאן מתגלה אי-יציבות בסדר, אם יש
            {"family_id": fid, "amount": 7, "type": "savings", "date": f"{YEAR}-{MONTH:02d}-20",
             "description": f"{marker}-same-day"},
        ]
        for r in rows:
            created["transactions"].append(_table("transactions").insert(r).execute().data[0]["id"])

        yield family_a
    finally:
        db.set_auth_token(family_a["token"])
        for table in ("transactions", "project_categories", "projects", "categories"):
            for row_id in created[table]:
                try:
                    _table(table).delete().eq("id", row_id).execute()
                except Exception:
                    pass


def _old_path(fid):
    """חמש השליפות, בדיוק כפי ש-month_view קרא להן."""
    return {
        "settings":   db.get_family_settings(fid),
        "members":    db.get_family_members(fid),
        "categories": db.get_categories(fid),
        "rows":       db.fetch_month_rows(fid, YEAR, MONTH),
        "archive":    db.get_months_archive(fid),
    }


def test_settings_members_categories_archive_match(month_fixture):
    """מה שהשוואת הקטגוריות כאן **לא** מכסה, ולמה.

    שני המסלולים שולפים ‎family_id is null or family_id = X‎ — הקטגוריות
    הגלובליות שנזרעות לכולם. במסד אין אף אחת כזאת (0 מתוך 17, נבדק
    23.9.2026), אז הענף הזה מת בשני הצדדים והשוואה לא יכולה להבחין בו:
    מוטציה שמסירה אותו לגמרי מהפונקציה החדשה עוברת את הבדיקה הזאת.

    זה לא פגם בפונקציה — היא מעתיקה את התנאי הישן נאמנה — אבל מי שיזרע
    קטגוריות גלובליות בעתיד צריך לדעת שאין כאן רשת."""
    fid = month_fixture["family_id"]
    db.set_auth_token(month_fixture["token"])

    old = _old_path(fid)
    new = db.fetch_month_page(fid, YEAR, MONTH)

    assert new["settings"]   == old["settings"]
    assert new["members"]    == old["members"]
    assert new["categories"] == old["categories"]
    assert new["archive"]    == old["archive"]


def test_month_rows_match_exactly(month_fixture):
    """תוכן השורות, כולל המבנה המקונן. ממוין לפי מזהה כדי שהשוואת התוכן
    לא תיפול על סדר — הסדר עצמו נבדק בנפרד למטה."""
    fid = month_fixture["family_id"]
    db.set_auth_token(month_fixture["token"])

    old_rows = sorted(db.fetch_month_rows(fid, YEAR, MONTH), key=lambda r: r["id"])
    new_rows = sorted(db.fetch_month_page(fid, YEAR, MONTH)["rows"], key=lambda r: r["id"])

    assert len(new_rows) == len(old_rows) > 0
    for old_row, new_row in zip(old_rows, new_rows):
        assert new_row == old_row, f"row {old_row['id']} differs"


def test_nested_joins_are_null_not_empty(month_fixture):
    """העסקה בלי קישורים: ‎None‎ ולא ‎{}‎. התבניות בודקות קיום, ו-‎{}‎
    שקרי היה מציג קטגוריה ריקה במקום לדלג."""
    fid = month_fixture["family_id"]
    db.set_auth_token(month_fixture["token"])

    rows = db.fetch_month_page(fid, YEAR, MONTH)["rows"]
    bare = [r for r in rows if r["description"].endswith("-bare")]
    assert len(bare) == 1
    for key in ("categories", "project_categories", "profiles", "projects"):
        assert bare[0][key] is None, f"{key} should be None on an unlinked row"

    linked = [r for r in rows if r["description"].endswith("-with-cat")][0]
    assert linked["categories"]["icon"] == "🧪"
    assert linked["profiles"] is not None
    assert linked["projects"] is None


def test_rows_are_ordered_newest_first(month_fixture):
    fid = month_fixture["family_id"]
    db.set_auth_token(month_fixture["token"])

    dates = [r["date"] for r in db.fetch_month_page(fid, YEAR, MONTH)["rows"]]
    assert dates == sorted(dates, reverse=True)


def test_other_family_gets_nothing(month_fixture, family_b):
    """הבדיקה שמצדיקה את ‎SECURITY DEFINER‎: הפונקציה עוקפת RLS, אז ההגנה
    היחידה היא ‎get_my_family_id()‎ שבתוכה. משפחה ב' שמבקשת את המזהה של
    משפחה א' חייבת לקבל כשל — לא נתונים, וגם לא "משפחה ריקה"."""
    fid = month_fixture["family_id"]

    db.set_auth_token(family_b["token"])
    with pytest.raises(db.DataUnavailable):
        db.fetch_month_page(fid, YEAR, MONTH)

    # בקרת-נגד: בלעדיה הבדיקה עוברת גם אם הקריאה נכשלת תמיד, מכל סיבה
    # שהיא — ואז היא לא בודקת את ההגנה אלא את זה שה-RPC שבור.
    own = db.fetch_month_page(family_b["family_id"], YEAR, MONTH)
    assert own["settings"], "family B must still be able to read its own month"
