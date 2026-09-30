""""עסקאות אחרונות" בדף הבית, מחולקות לפי יום (מתן, 30.9 — רעיון 2).

כותרת קטנה מעל כל יום — "היום", "אתמול", "ראשון, 27.9" — במקום תאריך
בכל שורה.
"""
import datetime

import pytest

from backend import app as app_module
from backend import supabase_config as db
from backend.app import app
from backend.wording import day_label

pytestmark = pytest.mark.unit

_TODAY = datetime.date(2026, 9, 30)   # יום רביעי


@pytest.mark.parametrize("date, expected", [
    ("2026-09-30", "היום"),
    ("2026-09-29", "אתמול"),
    ("2026-09-27", "ראשון, 27.9"),
    ("2026-09-26", "שבת, 26.9"),
    ("2026-08-03", "שני, 3.8"),
    ("2025-12-31", "רביעי, 31.12.2025"),   # שנה אחרת — עם השנה
])
def test_day_label(date, expected):
    assert day_label(date, _TODAY) == expected


def test_a_bad_date_does_not_break_the_page():
    assert day_label("", _TODAY) == ""
    assert day_label(None, _TODAY) == ""


_FAM = "11111111-1111-1111-1111-111111111111"
_ME  = "22222222-2222-2222-2222-222222222222"


def _tx(n, date, desc=""):
    return {"id": f"t{n}", "type": "expense", "amount": 10 * n, "date": date,
            "description": desc, "category_name": f"קט{n}", "category_icon": "🛒",
            "is_recurring": False, "user_id": None}


@pytest.fixture
def home(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setattr(db, "set_auth_token", lambda t: None)
    monkeypatch.setattr(db, "materialize_recurring", lambda fid: (0, True))
    monkeypatch.setattr(db, "get_family", lambda *a, **k: {"id": _FAM})
    monkeypatch.setattr(app_module, "family_settings", lambda: dict(db.DEFAULT_FAMILY_SETTINGS))
    monkeypatch.setattr(app_module.clock, "today", lambda: _TODAY)
    summary = {"income": 100.0, "expense": 60.0, "savings": 0.0, "balance": 40.0,
               "remaining": 40.0, "expense_pct": 60}
    for fn, val in (("get_family_settings", dict(db.DEFAULT_FAMILY_SETTINGS)),
                    ("get_categories", [{"id": "c", "name": "x", "type": "expense"}]),
                    ("get_family_members", []), ("family_has_no_transactions", False),
                    ("get_monthly_summary", summary), ("get_home_budgets", [])):
        monkeypatch.setattr(db, fn, lambda *a, _v=val, **k: _v)

    def render(transactions):
        monkeypatch.setattr(db, "get_recent_transactions", lambda *a, **k: transactions)
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["user_id"] = _ME
                sess["family_id"] = _FAM
            html = c.get("/").get_data(as_text=True)
        return html[html.index('class="transactions-list'):html.index("</ul>", html.index('class="transactions-list'))]
    return render


def test_one_header_per_day_in_order(home):
    lst = home([_tx(1, "2026-09-30", "רמי לוי"), _tx(2, "2026-09-30"),
                _tx(3, "2026-09-29"), _tx(4, "2026-09-27")])

    assert lst.count('class="tx-day') == 3
    assert lst.index("היום") < lst.index("קט1") < lst.index("קט2") < lst.index("אתמול") \
        < lst.index("קט3") < lst.index("ראשון, 27.9") < lst.index("קט4")


def test_the_row_no_longer_repeats_the_date(home):
    lst = home([_tx(1, "2026-09-30", "רמי לוי"), _tx(2, "2026-09-29")])

    assert "30.09" not in lst and "29.09" not in lst
    assert "רמי לוי" in lst


def test_newest_date_first_even_when_entered_out_of_order(home):
    """השרת מחזיר לפי סדר ההזנה. מי שהזין קודם את היום ואחר כך את
    אתמול היה מקבל "היום", "אתמול", ושוב "היום"."""
    lst = home([_tx(1, "2026-09-27"), _tx(2, "2026-09-29"), _tx(3, "2026-09-30"),
                _tx(4, "2026-09-30")])

    assert lst.count('class="tx-day') == 3
    assert lst.index("היום") < lst.index("אתמול") < lst.index("ראשון, 27.9")
    # בתוך יום — סדר ההזנה נשמר
    assert lst.index("קט3") < lst.index("קט4")
