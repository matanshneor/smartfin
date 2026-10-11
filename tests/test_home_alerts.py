"""התראות החודש גם בבית (מתן, 11.10).

כשיש התראות, הן מופיעות בדף הבית — אותן התראות כמו בעמוד החודש, מאותה
פונקציה (‎db.month_alerts‎). כשאין, אין שום אזור ריק. לחיצה על התראה
מובילה ליעד שלה בעמוד החודש: הקטגוריה שחרגה (‎#cat-<id>‎, נפתחת עם
העסקאות שלה), פירוט ההוצאות, או ראש העמוד — שם המאזן.
"""
from pathlib import Path

import pytest

from backend import app as app_module
from backend import supabase_config as db
from backend.app import app

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_FAM = "11111111-1111-1111-1111-111111111111"
_ME  = "22222222-2222-2222-2222-222222222222"
_FOOD = "33333333-3333-3333-3333-333333333333"


def _read(rel):
    return (_ROOT / rel).read_text(encoding="utf-8")


def _summary(income, expense, savings=0.0):
    return {"income": income, "expense": expense, "savings": savings,
            "remaining": round(income - expense - savings, 2)}


# ─── היעד של כל התראה ────────────────────────────────────────────────────

def test_a_budget_alert_leads_to_its_category():
    rows = [{"category_id": _FOOD, "name": "סופר", "icon": "🛒", "total": 2350}]
    settings = {"limits": {_FOOD: {"amount": 2000}}}
    alerts = db.budget_alerts(db.apply_budgets(rows, settings))
    assert [a["target"] for a in alerts] == [f"cat-{_FOOD}"]


def test_an_above_average_category_leads_to_its_category(monkeypatch):
    monkeypatch.setattr(db, "_category_history_averages", lambda *a: (
        {_FOOD: 3000.0}, {_FOOD: {"2026-07": 1000, "2026-08": 1000, "2026-09": 1000}},
        {_FOOD: {"name": "סופר", "icon": "🛒"}}))
    alerts = db.get_anomalies(_FAM, 2026, 10, _summary(10000, 3000))
    assert [a["target"] for a in alerts] == [f"cat-{_FOOD}"]


def test_expenses_above_income_lead_to_the_expenses(monkeypatch):
    monkeypatch.setattr(db, "_category_history_averages", lambda *a: ({}, {}, {}))
    alerts = db.get_anomalies(_FAM, 2026, 10, _summary(1000, 1500))
    assert [a["target"] for a in alerts] == ["expense-breakdown"]


def test_a_negative_balance_leads_to_the_balance_at_the_top(monkeypatch):
    monkeypatch.setattr(db, "_category_history_averages", lambda *a: ({}, {}, {}))
    alerts = db.get_anomalies(_FAM, 2026, 10, _summary(1000, 800, savings=500))
    assert [a["target"] for a in alerts] == [None]


def test_an_uncategorized_alert_falls_back_to_the_expenses():
    assert db.category_anchor(None) == "expense-breakdown"
    assert db.category_anchor(_FOOD) == f"cat-{_FOOD}"


def test_budget_categories_skip_the_average_alert(monkeypatch):
    """אותו כלל כמו קודם בעמוד החודש — עכשיו במקום אחד, לשני המסכים."""
    seen = {}
    monkeypatch.setattr(db, "get_anomalies",
                        lambda *a, skip_categories=None, **k: seen.setdefault("skip", skip_categories) and [])
    breakdown = [{"category_id": _FOOD, "budget": 2000}, {"category_id": "other"}]
    db.month_alerts(_FAM, 2026, 10, _summary(1, 0), {}, breakdown)
    assert seen["skip"] == [_FOOD]


# ─── דף הבית ─────────────────────────────────────────────────────────────

@pytest.fixture
def home(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setattr(db, "set_auth_token", lambda t: None)
    monkeypatch.setattr(db, "materialize_recurring", lambda fid: (0, True))
    monkeypatch.setattr(app_module, "family_settings", lambda: dict(db.DEFAULT_FAMILY_SETTINGS))
    for fn, val in (("get_family_settings", dict(db.DEFAULT_FAMILY_SETTINGS)),
                    ("get_categories", [{"id": _FOOD, "name": "סופר", "type": "expense"}]),
                    ("family_has_no_transactions", False), ("get_monthly_summary", _summary(9000, 1200)),
                    ("week_spending", None), ("fetch_month_rows", []), ("get_recent_transactions", []),
                    ("get_family_members", [{"id": _ME, "name": "מתן"}])):
        monkeypatch.setattr(db, fn, lambda *a, _v=val, **k: _v)

    def render(alerts):
        monkeypatch.setattr(db, "month_alerts", lambda *a, **k: list(alerts))
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["user_id"] = _ME
                sess["family_id"] = _FAM
            res = c.get("/")
            assert res.status_code == 200
            return res.get_data(as_text=True)
    return render


def test_no_alerts_no_empty_area(home):
    html = home([])
    assert 'class="alerts-section"' not in html


def test_each_alert_on_the_home_page_links_to_its_target(home):
    html = home([
        {"severity": "warning", "text": "🛒 סופר: חריגה", "target": f"cat-{_FOOD}"},
        {"severity": "danger", "text": "ההוצאות גבוהות מההכנסות", "target": "expense-breakdown"},
        {"severity": "danger", "text": "מאזן החודש שלילי", "target": None},
    ])
    assert 'class="alerts-section"' in html
    assert f'<a class="alert-card warning"\n       href="/month#cat-{_FOOD}">' in html
    assert '<a class="alert-card danger"\n       href="/month#expense-breakdown">' in html
    assert '<a class="alert-card danger"\n       href="/month">' in html


def test_a_failure_in_the_alerts_does_not_take_the_home_page_down(home, monkeypatch):
    def boom(*a, **k):
        raise db.DataUnavailable("x")
    monkeypatch.setattr(db, "fetch_month_rows", boom)
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = _ME
            sess["family_id"] = _FAM
        assert c.get("/").status_code == 200


# ─── עמוד החודש ──────────────────────────────────────────────────────────

def test_the_month_page_has_an_anchor_per_category_and_alerts_are_links():
    tpl = _read("frontend/templates/month.html")
    assert '<li class="legend-item-wrap"{% if item.category_id %} id="cat-{{ item.category_id }}"{% endif %}>' in tpl
    assert '<a class="alert-card {{ alert.severity }}" href="#{{ alert.target or \'top\' }}">' in tpl


def test_arriving_at_a_category_opens_it():
    js = _read("frontend/static/js/month.js")
    assert "else if (arrived.indexOf('cat-') === 0) showCategory(arrived, false);" in js
    body = js[js.index("function showCategory"):]
    body = body[:body.index("\n}\n")]
    assert "toggleExpand(trigger)" in body and "flashBreakdown('expense-breakdown')" in body
