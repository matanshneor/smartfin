"""סוג בלי עסקאות בעמוד החודש — שורה אחת, לא כרטיס ריק (מתן, 11.10).

"אין הפרשות לחיסכון החודש" ישב בכרטיס שלם בגובה חצי מסך. הריבוע למעלה
כבר אומר ₪0, אז מה שנשאר לכרטיס לעשות הוא לאשר שזה לא באג — ושורה עושה
את זה. "+ הוספה" בשורה פותח את חלון ההוספה על הסוג שלה.
"""
from pathlib import Path

import pytest

from backend import supabase_config as db
from backend.app import app

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent


def _tx(type_):
    return {"id": type_, "type": type_, "amount": 50, "date": "2026-09-01", "description": "x",
            "category_name": "c", "category_icon": "🍔", "user_id": None, "user_name": "",
            "is_recurring": False, "project_id": None, "has_receipt": False,
            "recurring_parent_id": None, "workplace": None, "recurring_frequency": None,
            "project_name": None, "project_icon": None, "category_id": None,
            "project_category_id": None, "recurring_end_date": None}


def _render(transactions, income_sources=(), savings_home=(), income_breakdown=(), savings_breakdown=()):
    ctx = dict(
        active_page="month", user={"id": "x", "name": "מתן", "avatar_initial": "מ"},
        summary={"income": 0, "expense": 0, "savings": 0, "balance": 0, "remaining": 0, "expense_pct": 0},
        expense_breakdown=[], income_breakdown=list(income_breakdown),
        savings_breakdown=list(savings_breakdown), income_sources=list(income_sources),
        savings_home=list(savings_home), member_breakdowns=[], member_colors={},
        month_label="ספטמבר 2026", year=2026, month=9, is_current=True,
        strip_months=[], hebrew_months=["", "ינואר"],
        project_month={"transactions": [], "expense": 0, "income": 0},
        summary_data={}, expense_data={}, members_data={},
        family_settings=dict(db.DEFAULT_FAMILY_SETTINGS),
    )
    with app.test_request_context("/month"):
        return app.jinja_env.get_template("month.html").render(month_transactions=transactions, **ctx)


def _row(html, anchor):
    start = html.index(f'<div class="empty-row" id="{anchor}">')
    return html[start:html.index("</div>", start)]


def test_no_savings_is_one_row_with_add():
    html = _render([_tx("expense")])
    row = _row(html, "savings-breakdown")
    assert "💰" in row and "אין חיסכון החודש" in row
    assert 'data-add-type="savings"' in row and "+ הוספה" in row
    assert "אין הפרשות לחיסכון החודש" not in html     # הכרטיס הריק הישן


def test_no_income_is_one_row_with_add():
    html = _render([_tx("expense")])
    row = _row(html, "income-breakdown")
    assert "💼" in row and "אין הכנסות החודש" in row and 'data-add-type="income"' in row


def test_a_type_with_data_keeps_its_card():
    src = {"label": "משכורת", "icon": "💼", "color": "#000", "pct": 100, "total": 9000, "transactions": []}
    sav = {"name": "קרן", "icon": "🏦", "color": "#000", "share": 100, "total": 500}
    html = _render([_tx("income"), _tx("savings")], income_sources=[src], savings_home=[sav])
    assert 'class="empty-row"' not in html
    assert '<section class="chart-card" id="income-breakdown">' in html
    assert '<section class="chart-card" id="savings-breakdown">' in html


def test_project_only_savings_still_get_the_card():
    """חיסכון שכולו בפרויקט — הכרטיס מציג את שורת הפרויקט, אז הוא נשאר."""
    proj = {"name": "טיול", "icon": "✈️", "total": 800, "is_project": True, "project_id": "p"}
    html = _render([_tx("expense")], savings_breakdown=[proj])
    assert '<section class="chart-card" id="savings-breakdown">' in html
    assert '<div class="empty-row" id="savings-breakdown">' not in html


def test_expenses_keep_their_card_even_when_empty():
    """בכרטיס ההוצאות יושבים "קביעת תקציבים" ורשימת הקטגוריות — לא מחליפים
    אותו בשורה."""
    html = _render([_tx("income")])
    assert '<section class="chart-card" id="expense-breakdown">' in html
    assert 'data-add-type="expense"' not in html


def test_add_opens_the_window_on_that_type():
    js = (_ROOT / "frontend/static/js/transactions.js").read_text(encoding="utf-8")
    assert "const preset = typeof presetType === 'string' ? presetType : null;" in js
    assert "const type = preset ? preset" in js
    assert "if (btn) openAddModal(btn.dataset.addType);" in js
