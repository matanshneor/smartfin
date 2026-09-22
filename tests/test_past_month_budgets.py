"""חודש שנגמר הציג תקציב כאילו הוא עדיין פתוח.

מתן שאל: "האם בעמוד של חודשים קודמים צריך להופיע לי עבור כל קטגוריה
'קביעת תקציב לקטגוריה'? נראה לי שלא קובעים תקציב לחודשים שעברו."

הוא צדק, והשורש מתחת לזה גדול מהקישור: **התקציב נשמר כמפה גלובלית
לפי קטגוריה** (‎families.settings.limits‎) — בלי חודש ובלי היסטוריה.
מכאן שתי תקלות נפרדות בעמוד אחד:

1. הקישור הבטיח משהו שלא קורה. לחיצה מתוך מרץ פותחת את ההגדרות
   וקובעת סכום שמשפיע **מהיום והלאה**; מרץ לא ישתנה. המסך רומז
   שמתקצבים את החודש שרואים.

2. וגם כשכבר יש תקציב, חודש שעבר אמר "נשאר ₪500 מתוך ₪2,000". בחודש
   שנגמר אין "נשאר" — אין מה להוציא. ה-₪2,000 הוא גם התקציב של היום,
   לא בהכרח מה שהיה אז.

הבדיקות כאן מרנדרות את התבנית האמיתית ובודקות את מה שנראה על המסך,
ולא את הקוד שאמור לייצר אותו.
"""
from pathlib import Path

import pytest

from backend.app import app
from backend import supabase_config as db

pytestmark = pytest.mark.unit

_CAT = "cat-groceries"


# התבנית קוראת ל-‎item.name/icon‎ ומסננת ל-‎total > 0‎.
def _row(spent):
    return {"category_id": _CAT, "name": "מכולת", "icon": "🛒",
            "total": spent, "pct": 40, "is_project": False}


def _breakdown(spent, budget=2000):
    """שורת פילוח אמיתית, דרך אותה פונקציה שמריצה את הייצור."""
    settings = {"limits": {_CAT: {"amount": budget, "alert": True}}}
    return db.apply_budgets([_row(spent)], settings)


def _render(breakdown, is_current):
    ctx = dict(
        active_page="month", user={"id": "x", "name": "מתן", "avatar_initial": "מ"},
        summary={"income": 10000, "expense": 5000, "savings": 0, "balance": 5000,
                 "remaining": 5000, "expense_pct": 50},
        expense_breakdown=breakdown, income_breakdown=[], savings_breakdown=[],
        member_breakdowns=[], anomalies=[], member_colors={},
        month_label="מרץ 2026", year=2026, month=3, is_current=is_current,
        strip_months=[], hebrew_months=["", "ינואר"],
        project_month={"transactions": [], "expense": 0, "income": 0},
        summary_data={}, expense_data=[], members_data=[],
        family_settings=dict(db.DEFAULT_FAMILY_SETTINGS),
    )
    tx = {"id": "1", "type": "expense", "amount": 1240, "date": "2026-03-04",
          "description": "קניות", "category_name": "מכולת", "category_icon": "🛒",
          "user_id": None, "user_name": "משותף", "is_recurring": False,
          "project_id": None, "has_receipt": False, "recurring_parent_id": None,
          "workplace": None, "recurring_frequency": None, "project_name": None,
          "project_icon": None, "category_id": _CAT, "project_category_id": None,
          "recurring_end_date": None}
    with app.test_request_context("/month"):
        return app.jinja_env.get_template("month.html").render(
            month_transactions=[tx], **ctx)


# ─── הקישור ──────────────────────────────────────────────────────────────────

def test_a_closed_month_does_not_offer_to_budget_it():
    """השאלה של מתן."""
    rows = [_row(1240)]

    assert "קביעת תקציב לקטגוריה" not in _render(rows, is_current=False)


def test_the_current_month_still_offers_it():
    """זה הרגע שבו אדם מבין שהוא צריך תקציב — הוא רואה ₪1,240 על
    מכולת. להסיר את זה מהחודש הנוכחי יקבור את התכונה המרכזית חזרה
    מאחורי ארבעה מסכים."""
    rows = [_row(1240)]

    assert "קביעת תקציב לקטגוריה" in _render(rows, is_current=True)


# ─── הניסוח ──────────────────────────────────────────────────────────────────

def _budget_text(html):
    """רק שורת התקציב. המילה "נשאר" מופיעה גם ב"נשאר בעו״ש החודש"
    במקום אחר בעמוד, ובדיקה על כל ה-HTML הייתה נכשלת עליה."""
    import re
    m = re.search(r'<p class="cat-budget-text">(.*?)</p>', html, re.S)
    assert m, "שורת התקציב לא רונדרה בכלל"
    return " ".join(m.group(1).split())


def test_a_closed_month_does_not_say_what_is_left_to_spend():
    """הלב. "נשאר ₪500" על מרץ הוא משפט על היום, מודבק על העבר."""
    text = _budget_text(_render(_breakdown(spent=1500), is_current=False))

    assert "נשאר" not in text, f"עדיין לשון הווה: {text}"
    assert text == "₪1,500 מתוך תקציב של ₪2,000"


def test_the_current_month_still_says_what_is_left():
    html = _render(_breakdown(spent=1500), is_current=True)

    assert _budget_text(html) == "נשאר ₪500 מתוך ₪2,000"


def test_an_overrun_reads_the_same_either_way():
    """"חריגה של ₪300" נכון בשני הזמנים, ואין סיבה לנסח אותו פעמיים."""
    over_now = _render(_breakdown(spent=2300), is_current=True)
    over_then = _render(_breakdown(spent=2300), is_current=False)

    for html in (over_now, over_then):
        assert _budget_text(html) == "חריגה של ₪300 מתוך ₪2,000"


def test_the_bar_itself_still_appears_in_a_closed_month():
    """ההחלטה הייתה לשמור את הפס ולשנות רק את המילים — בלעדיו אי אפשר
    להסתכל אחורה ולראות איפה חרגת."""
    import re
    html = _render(_breakdown(spent=1500), is_current=False)

    bar = re.search(r'<div class="cat-budget[ "].*?</div>\s*</div>', html, re.S)
    assert bar, "אזור התקציב לא רונדר"
    bar = bar.group(0)

    assert "cat-budget-track" in bar and "cat-budget-fill" in bar
    # "קיים ב-HTML" אינו "נראה על המסך". מוטציה ששמה ‎display:none‎
    # על המסלול שרדה את הגרסה הראשונה של הבדיקה הזאת.
    assert "display:none" not in bar.replace(" ", "")
    assert 'width: 75%' in bar, f"הפס לא משקף 1,500 מתוך 2,000: {bar}"


def test_the_number_shown_is_what_was_actually_spent():
    """‎budget_left‎ הוא מה שנשאר, לא מה שיצא. שימוש בו בניסוח החדש
    היה הופך "הוצאת ₪1,500" ל"הוצאת ₪500"."""
    text = _budget_text(_render(_breakdown(spent=1500, budget=2000), is_current=False))

    assert "₪1,500 מתוך" in text
    assert "₪500 מתוך" not in text
