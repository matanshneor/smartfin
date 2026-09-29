"""התראת "גבוהה מהממוצע" מקובצת לפי מזהה הקטגוריה, לא לפי שמה.

לפי שם, שני דברים השתבשו:
- עסקה בלי קטגוריה נספרה תחת "אחר" — ₪800 שלא סווגו הפכו ל"ההוצאה על
  אחר גבוהה ב-700%", על קטגוריה שבה לא הוצאת כלום.
- שתי קטגוריות באותו שם התמזגו לאחת, והממוצע של אחת נמדד מול החודש של
  השנייה.
"""
import pytest

from backend import supabase_config as db

from tests._fake_db import FakeSupabase

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"
_SUMMARY = {"income": 100000, "expense": 0, "remaining": 100000}
_SETTINGS = {**db.DEFAULT_FAMILY_SETTINGS,
             "anomaly": {"enabled": True, "percent": 150, "min_gap": 300}}


def _row(date, amount, cat_id=None, name=None, icon="📦"):
    return {"family_id": _FAM, "type": "expense", "project_id": None,
            "date": date, "amount": amount, "category_id": cat_id,
            "categories": {"name": name, "icon": icon} if cat_id else None}


def _alerts(monkeypatch, rows, **kw):
    monkeypatch.setattr(db, "get_client", lambda: FakeSupabase(transactions=rows))
    return [a["text"] for a in db.get_anomalies(_FAM, 2026, 9, _SUMMARY, _SETTINGS, **kw)]


def test_uncategorized_money_does_not_inflate_other(monkeypatch):
    history = [_row(f"2026-0{m}-10", 100, "other", "אחר") for m in (6, 7, 8)]
    texts = _alerts(monkeypatch, history + [
        _row("2026-09-10", 100, "other", "אחר"),
        _row("2026-09-11", 800),                     # בלי קטגוריה
    ])

    # "אחר" לא זז (₪100 כמו תמיד), ול-₪800 שלא סווגו אין היסטוריה להשוות אליה
    assert texts == [], texts


def test_same_named_categories_are_measured_separately(monkeypatch):
    """"מסעדות" של כרטיס א' בחודשים הקודמים, "מסעדות" אחרת החודש."""
    history = [_row(f"2026-0{m}-10", 1000, "a", "מסעדות") for m in (6, 7, 8)]
    texts = _alerts(monkeypatch, history + [
        _row("2026-09-10", 1000, "a", "מסעדות"),
        _row("2026-09-11", 1000, "b", "מסעדות"),
    ])

    assert texts == [], texts


def test_a_real_jump_still_alerts(monkeypatch):
    """בקרת-נגד: בלעדיה שתי הבדיקות למעלה עוברות גם כשההתראה מתה."""
    history = [_row(f"2026-0{m}-10", 1000, "a", "מסעדות", "🍽") for m in (6, 7, 8)]
    texts = _alerts(monkeypatch, history + [_row("2026-09-10", 3000, "a", "מסעדות", "🍽")])

    assert len(texts) == 1 and "🍽 ההוצאה על מסעדות" in texts[0], texts


def test_skip_is_by_category_id(monkeypatch):
    history = [_row(f"2026-0{m}-10", 1000, "a", "מסעדות") for m in (6, 7, 8)]
    rows = history + [_row("2026-09-10", 3000, "a", "מסעדות")]

    assert _alerts(monkeypatch, rows, skip_categories=["a"]) == []
    assert _alerts(monkeypatch, rows, skip_categories=["מסעדות"]) != []
