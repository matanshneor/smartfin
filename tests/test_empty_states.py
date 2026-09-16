"""
בדיקות למסכים ריקים.

משפחה חדשה נוחתת בעמוד החודש ישר מהדשבורד ורואה חמישה כרטיסי גרף ריקים
בזה אחר זה, בלי שום הסבר — מסך שנראה שבור. זה קורה פעם אחת לכל משפחה,
והפעם הזאת היא שקובעת אם הם יישארו.

כל שאר העמודים כבר מטפלים במצב הזה; עמוד החודש היה היחיד שנשכח. הבדיקה
האחרונה כאן היא זו שתתפוס את העמוד הבא שיישכח.
"""
from pathlib import Path

import pytest

from backend.app import app
from backend import supabase_config as db

pytestmark = pytest.mark.unit

_TPL = Path(__file__).resolve().parent.parent / "frontend/templates"

_TX = {
    "id": "1", "type": "expense", "amount": 50, "date": "2026-09-01",
    "description": "x", "category_name": "מזון", "category_icon": "🍔",
    "user_id": None, "user_name": "משותף", "is_recurring": False,
    "project_id": None, "has_receipt": False, "recurring_parent_id": None,
    "workplace": None, "recurring_frequency": None, "project_name": None,
    "project_icon": None, "category_id": None, "project_category_id": None,
    "recurring_end_date": None,
}


def _render_month(transactions, is_current=True):
    ctx = dict(
        active_page="month", user={"id": "x", "name": "מתן", "avatar_initial": "מ"},
        summary={"income": 0, "expense": 0, "savings": 0, "balance": 0,
                 "remaining": 0, "expense_pct": 0},
        expense_breakdown=[], income_breakdown=[], savings_breakdown=[],
        member_breakdowns=[], anomalies=[], member_colors={},
        month_label="ספטמבר 2026", year=2026, month=9, is_current=is_current,
        strip_months=[], hebrew_months=["", "ינואר"],
        project_month={"transactions": [], "expense": 0, "income": 0},
        summary_data={}, expense_data={}, members_data={},
        family_settings=dict(db.DEFAULT_FAMILY_SETTINGS),
    )
    with app.test_request_context("/month"):
        return app.jinja_env.get_template("month.html").render(
            month_transactions=transactions, **ctx)


def test_a_month_with_nothing_in_it_explains_itself():
    html = _render_month([])

    assert "empty-state" in html
    assert "אין עדיין עסקאות החודש" in html


def test_it_does_not_render_five_blank_charts():
    """זה מה שהמשתמש ראה בפועל: חמישה כרטיסים ריקים בזה אחר זה."""
    html = _render_month([])

    assert html.count('"chart-card"') == 1


def test_an_empty_month_does_not_download_chart_js():
    """‎70KB דחוסים שאין מה לצייר איתם."""
    assert "chart.umd" not in _render_month([])


def test_a_past_month_offers_the_way_back():
    """'לא נרשמו עסקאות באוגוסט' בלי דרך חזרה הוא מבוי סתום."""
    html = _render_month([], is_current=False)

    assert "לחזור לחודש הנוכחי" in html


def test_a_month_with_data_is_untouched():
    """בקרת-נגד: הגרפים והספרייה חייבים לחזור ברגע שיש מה להציג."""
    html = _render_month([_TX])

    assert "empty-state" not in html
    assert html.count('"chart-card"') == 5
    assert "chart.umd" in html


def test_every_page_that_can_be_empty_says_so():
    """זו הבדיקה שתתפוס את העמוד הבא שיישכח."""
    for page in ("index.html", "month.html", "months.html",
                 "projects.html", "project_detail.html", "settings.html"):
        html = (_TPL / page).read_text(encoding="utf-8")
        assert "empty-state" in html, f"{page} ללא מצב ריק"
