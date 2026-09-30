""""המאזן החודשי שלילי" בחודש שעוד אין בו הכנסות (מתן, 30.9).

המאזן עצמו מוצג "—" כשאין הכנסות — זה לא גירעון, פשוט עוד אין ממה
להחסיר. ההתראה האדומה מתחתיו אמרה את ההפך. עכשיו אותו כלל לשניהם.
"""
import pytest

from backend import supabase_config as db

pytestmark = pytest.mark.unit


def _alerts(monkeypatch, **summary):
    monkeypatch.setattr(db, "_category_history_averages", lambda *a: ({}, {}, {}))
    base = {"income": 0.0, "expense": 0.0, "savings": 0.0}
    base.update(summary)
    base["remaining"] = round(base["income"] - base["expense"] - base["savings"], 2)
    return [a["text"] for a in db.get_anomalies("fam", 2026, 9, base)]


def test_no_income_yet_is_not_a_negative_balance(monkeypatch):
    assert not any("שלילי" in t for t in _alerts(monkeypatch, expense=2140))


def test_a_real_negative_balance_still_warns(monkeypatch):
    """בקרת-נגד: יש הכנסות, והחיסכון וההוצאות עברו אותן."""
    assert any("שלילי" in t for t in _alerts(monkeypatch, income=5000, expense=4000, savings=2000))


def test_less_than_a_shekel_below_is_not_negative(monkeypatch):
    """אותו עיגול כמו המאזן שמוצג — ‎-₪0‎ באדום היה אותה סתירה."""
    assert not any("שלילי" in t for t in _alerts(monkeypatch, income=1000, expense=1000.4))
