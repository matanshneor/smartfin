"""כרטיס "תקציבים החודש" בדף הבית (מתן, 30.9 — אפשרות א).

עד 3 קטגוריות עם תקציב, הקרובה ביותר לגבול קודם (חריגה לפני הכל).
ירוק כשיש מקום, כתום מ-80%, אדום בחריגה. מי שלא קבע אף תקציב — אין כרטיס,
ואין גם שליפה.
"""
import pytest

from backend import app as app_module
from backend import supabase_config as db
from backend.app import app
from tests._fake_db import FakeSupabase

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"
_ME  = "22222222-2222-2222-2222-222222222222"

_CATS = [
    {"id": "food",  "name": "סופר",    "icon": "🛒", "type": "expense"},
    {"id": "fuel",  "name": "דלק",     "icon": "⛽", "type": "expense"},
    {"id": "rest",  "name": "מסעדות",  "icon": "🍽", "type": "expense"},
    {"id": "fun",   "name": "בילויים", "icon": "🎉", "type": "expense"},
    {"id": "gift",  "name": "מתנות",   "icon": "🎁", "type": "expense"},
]


def _tx(cat, amount, project=None, type_="expense"):
    return {"id": f"{cat}-{amount}", "family_id": _FAM, "type": type_, "amount": amount,
            "category_id": cat, "date": "2026-09-10", "project_id": project}


def _settings(**limits):
    s = dict(db.DEFAULT_FAMILY_SETTINGS)
    s["limits"] = {k: {"amount": v, "alert": True} for k, v in limits.items()}
    return s


def test_closest_to_the_limit_first_and_only_three(monkeypatch):
    monkeypatch.setattr(db, "get_client", lambda: FakeSupabase(transactions=[
        _tx("food", 1760), _tx("fuel", 380), _tx("rest", 650), _tx("fun", 100),
    ]))
    settings = _settings(food=2000, fuel=800, rest=500, fun=1000)

    rows = db.get_home_budgets(_FAM, 2026, 9, settings, _CATS)

    assert [r["category_id"] for r in rows] == ["rest", "food", "fuel"]
    assert rows[0]["budget_over"] and rows[0]["budget_excess"] == 150
    assert rows[1]["budget_left"] == 240


def test_project_money_does_not_count_against_the_budget(monkeypatch):
    """אותו כלל כמו כל סיכום חודשי — כסף פרויקט מוצג בנפרד."""
    monkeypatch.setattr(db, "get_client", lambda: FakeSupabase(transactions=[
        _tx("food", 500), _tx("food", 5000, project="p1"),
    ]))

    rows = db.get_home_budgets(_FAM, 2026, 9, _settings(food=2000), _CATS)

    assert rows[0]["budget_left"] == 1500


def test_a_budget_with_no_spending_yet_still_shows(monkeypatch):
    monkeypatch.setattr(db, "get_client", lambda: FakeSupabase(transactions=[]))

    rows = db.get_home_budgets(_FAM, 2026, 9, _settings(gift=300), _CATS)

    assert [r["category_id"] for r in rows] == ["gift"]
    assert rows[0]["budget_left"] == 300


def test_no_budgets_means_no_query(monkeypatch):
    def boom():
        raise AssertionError("שליפה בלי שיש תקציב")
    monkeypatch.setattr(db, "get_client", boom)

    assert db.get_home_budgets(_FAM, 2026, 9, _settings(), _CATS) == []


# ── התצוגה ────────────────────────────────────────────────────────────

@pytest.fixture
def home(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setattr(db, "set_auth_token", lambda t: None)
    monkeypatch.setattr(db, "materialize_recurring", lambda fid: (0, True))
    monkeypatch.setattr(db, "get_family", lambda *a, **k: {"id": _FAM})
    monkeypatch.setattr(app_module, "family_settings", lambda: dict(db.DEFAULT_FAMILY_SETTINGS))
    summary = {"income": 10000.0, "expense": 3000.0, "savings": 0.0, "balance": 7000.0,
               "remaining": 7000.0, "expense_pct": 30}
    for fn, val in (("get_categories", _CATS), ("get_family_members", []),
                    ("family_has_no_transactions", False), ("get_recent_transactions", []),
                    ("get_monthly_summary", summary)):
        monkeypatch.setattr(db, fn, lambda *a, _v=val, **k: _v)

    def render(settings, transactions):
        monkeypatch.setattr(db, "get_family_settings", lambda *a, **k: settings)
        monkeypatch.setattr(db, "get_client", lambda: FakeSupabase(transactions=transactions))
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["user_id"] = _ME
                sess["family_id"] = _FAM
            return c.get("/").get_data(as_text=True)
    return render


def test_the_card_shows_what_is_left_and_the_state(home):
    html = home(_settings(food=2000, fuel=800, rest=500),
                [_tx("food", 1760), _tx("fuel", 380), _tx("rest", 650)])

    card = html[html.index('home-budgets"'):]
    card = card[:card.index("</section>")]
    assert "תקציבים החודש" in card
    assert "חריגה של ₪150" in card
    assert "נשארו ₪240 מתוך ₪2,000" in card
    assert "נשארו ₪420 מתוך ₪800" in card
    # שלושה מצבים, שלושה צבעים
    assert 'budget-fill over' in card and 'budget-fill warn' in card and 'budget-fill ok' in card
    assert "#expense-breakdown" in card
    assert card.index("מסעדות") < card.index("סופר") < card.index("דלק")


def test_no_card_without_budgets(home):
    html = home(_settings(), [_tx("food", 1760)])

    assert "home-budgets" not in html
    assert "תקציבים החודש" not in html
