"""
עמוד החודש גזר את אותן שורות שוב ושוב.

שבע שאילתות נפרדות קראו את אותו טווח תאריכים של אותה משפחה, וכל אחת
חזרה וכתבה לעצמה את כללי הבית: פרויקט לא נכנס למאזן החודשי, עסקה בלי
בעלים היא "משותפת", פרויקט אישי של אחר לא מוצג בשמו. כלל שנכתב שבע
פעמים הוא כלל שישתנה בשש מהן — וכבר היה באג כזה.

עכשיו יש שליפה אחת וגזירות ממנה. הבדיקות כאן נועלות את הכללים במקום
אחד: אותם מספרים בדיוק, מאותן שורות.
"""
import pytest

from backend import supabase_config as db

pytestmark = pytest.mark.unit

_ME  = "11111111-1111-1111-1111-111111111111"
_YOU = "22222222-2222-2222-2222-222222222222"


def _row(type_, amount, *, cat=None, user=None, name=None, project=None):
    return {
        "id": f"{type_}-{amount}", "type": type_, "amount": amount,
        "date": "2026-09-10", "note": "",
        "user_id": user,
        "project_id": "p1" if project else None,
        "categories": {"name": cat, "icon": "🧾"} if cat else None,
        "project_categories": None,
        "profiles": {"name": name, "workplace": None} if name else None,
        "projects": project,
    }


ROWS = [
    _row("income",  10000, cat="משכורת", user=_ME,  name="מתן שניאור"),
    _row("expense",   400, cat="סופר",   user=_ME,  name="מתן שניאור"),
    _row("expense",   250, cat="סופר"),                      # משותפת
    _row("expense",   100, cat="דלק",    user=_YOU, name="אור לוי"),
    _row("savings",  1000, cat="קרן",    user=_ME,  name="מתן שניאור"),
    # עסקת פרויקט — בכוונה גדולה, כדי שתיראה בבירור אם תדלוף לסיכום
    _row("expense", 50000, cat="שיפוץ", user=_ME, name="מתן שניאור",
         project={"owner_id": _YOU, "name": "הפרויקט של אור", "icon": "🔨"}),
]

CATEGORIES = [
    {"name": "סופר", "icon": "🛒", "type": "expense"},
    {"name": "דלק",  "icon": "⛽", "type": "expense"},
    {"name": "חשמל", "icon": "💡", "type": "expense"},   # ללא הוצאה החודש
    {"name": "משכורת", "icon": "💰", "type": "income"},
]


# ─── הכלל שכל הסיכומים חולקים: פרויקט אינו חלק מהחודש הרגיל ────────────────

def test_a_project_expense_does_not_touch_the_monthly_balance():
    s = db.summary_from_rows(ROWS)
    assert s["income"]    == 10000
    assert s["expense"]   == 750      # 400 + 250 + 100, בלי 50,000 של הפרויקט
    assert s["savings"]   == 1000
    assert s["balance"]   == 9250
    assert s["remaining"] == 8250


def test_a_project_expense_does_not_touch_the_category_breakdown():
    names = {c["name"] for c in db.category_breakdown_from_rows(ROWS, CATEGORIES, "expense")}
    assert "שיפוץ" not in names, "הוצאת פרויקט נספרה בפילוח הקטגוריות"


def test_a_project_expense_does_not_touch_the_member_breakdown():
    total = sum(m["expense"] for m in db.member_breakdown_from_rows(ROWS, "expense"))
    assert total == 750


def test_a_project_expense_is_still_shown_in_the_list():
    """היא לא במאזן, אבל היא כן קרתה — מי שמסתכל על רשימת החודש צריך לראותה."""
    ids = {t["id"] for t in db.month_transactions_from_rows(ROWS, None, _YOU)}
    assert "expense-50000" in ids


# ─── פרטיות: פרויקט אישי של מישהו אחר ───────────────────────────────────────

def test_a_personal_project_of_someone_else_stays_out_of_the_list():
    ids = {t["id"] for t in db.month_transactions_from_rows(ROWS, None, _ME)}
    assert "expense-50000" not in ids, "עסקה מפרויקט אישי של אחר הוצגה"


def test_but_its_owner_does_see_it():
    ids = {t["id"] for t in db.month_transactions_from_rows(ROWS, None, _YOU)}
    assert "expense-50000" in ids


# ─── פירוט הקטגוריות ────────────────────────────────────────────────────────

def test_a_category_with_no_spending_this_month_is_still_listed_at_zero():
    """אחרת קטגוריה נעלמת מהעמוד בדיוק בחודש שבו לא הוצאת בה — ונראה
    כאילו נמחקה."""
    rows = {c["name"]: c for c in db.category_breakdown_from_rows(ROWS, CATEGORIES, "expense")}
    assert rows["חשמל"]["total"] == 0


def test_categories_are_ordered_by_size():
    out = db.category_breakdown_from_rows(ROWS, CATEGORIES, "expense")
    assert [c["name"] for c in out] == ["סופר", "דלק", "חשמל"]
    assert out[0]["total"] == 650      # 400 + 250, שתי שורות באותה קטגוריה
    assert out[0]["pct"]   == 87       # 650 מתוך 750


def test_income_and_expense_do_not_mix():
    out = db.category_breakdown_from_rows(ROWS, CATEGORIES, "income")
    assert [c["name"] for c in out] == ["משכורת"]
    assert out[0]["total"] == 10000


# ─── חלוקה בין בני המשפחה ───────────────────────────────────────────────────

def test_a_transaction_with_no_owner_is_shared():
    out = db.member_breakdown_from_rows(ROWS, "expense")
    assert {m["name"]: m["expense"] for m in out} == {
        "מתן": 400.0, "משותפת": 250.0, "אור": 100.0}


def test_members_are_ordered_by_size():
    assert [m["name"] for m in db.member_breakdown_from_rows(ROWS, "expense")] == \
        ["מתן", "משותפת", "אור"]


# ─── חודש ריק ───────────────────────────────────────────────────────────────

def test_an_empty_month_is_zero_and_not_a_crash():
    s = db.summary_from_rows([])
    assert s == {"income": 0.0, "expense": 0.0, "savings": 0.0,
                 "balance": 0.0, "remaining": 0.0, "expense_pct": 0}
    assert db.member_breakdown_from_rows([], "expense") == []
    assert db.month_transactions_from_rows([], None, _ME) == []
