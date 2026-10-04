"""חודש עתידי והחודש הנוכחי — מה מופיע בהם (מתן, 4.10).

עסקה קבועה מופיעה רק מהיום שהיא יורדת, כשהמנוע יוצר אותה כעסקה אמיתית —
לא מראש, לא בחודש הנוכחי ולא בחודש עתידי. עסקה שהוזנה ידנית בתאריך עתידי
היא שורה רגילה: מופיעה בחודש שלה, נספרת בו, ונפתחת לעריכה.

(עד 4.10 חודש עתידי הציג מראש את המופעים הצפויים — מתן, 30.9 — וזה בוטל.)
"""
import datetime

import pytest

from backend import app as app_module
from backend import supabase_config as db
from backend.app import app

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"
_ME  = "22222222-2222-2222-2222-222222222222"
_TODAY = datetime.date(2026, 10, 4)


def _row(id_, amount, date, name, icon, recurring=False):
    return {"id": id_, "family_id": _FAM, "amount": amount, "type": "expense", "date": date,
            "description": name, "user_id": None, "category_id": "c1", "project_id": None,
            "project_category_id": None, "is_recurring": recurring, "recurring_parent_id": None,
            "recurring_frequency": "monthly_15" if recurring else None,
            "recurring_end_date": None, "receipt_path": None, "workplace": None,
            "categories": {"name": name, "icon": icon},
            "project_categories": None, "profiles": None, "projects": None}


@pytest.fixture
def month_page(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setattr(db, "set_auth_token", lambda t: None)
    monkeypatch.setattr(db, "materialize_recurring", lambda fid: (0, True))
    monkeypatch.setattr(db, "get_anomalies", lambda *a, **k: [])
    monkeypatch.setattr(db, "get_family", lambda *a, **k: {"id": _FAM})
    monkeypatch.setattr(app_module, "family_settings", lambda: dict(db.DEFAULT_FAMILY_SETTINGS))
    monkeypatch.setattr(app_module.clock, "now", lambda: datetime.datetime(2026, 10, 4, 12, 0))
    monkeypatch.setattr(app_module.clock, "today", lambda: _TODAY)

    def render(real_rows, url):
        monkeypatch.setattr(db, "fetch_month_page", lambda fid, y, m: {
            "family": {"id": _FAM}, "settings": dict(db.DEFAULT_FAMILY_SETTINGS),
            "members": [{"id": _ME, "name": "מתן"}],
            "categories": [{"id": "c1", "name": "שכר דירה", "icon": "🏠", "type": "expense"}],
            "rows": real_rows, "archive": []})
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["user_id"] = _ME
                sess["family_id"] = _FAM
            res = c.get(url)
            assert res.status_code == 200
            return res.get_data(as_text=True)
    return render


@pytest.mark.parametrize("url", ["/month", "/month?year=2026&month=11"])
def test_a_recurring_series_adds_nothing_before_its_date(month_page, url):
    """התבנית עצמה מחודש ינואר לא בשורות החודש — ואין שום מופע צפוי."""
    html = month_page([], url)

    assert "empty-state" in html


def test_a_one_time_future_transaction_shows_in_its_month(month_page):
    trip = _row("trip", 1400, "2026-11-20", "טיסה", "✈️")
    html = month_page([trip], "/month?year=2026&month=11")

    assert "₪1,400" in html and "20.11" in html
    # עסקה אמיתית — נפתחת לעריכה
    assert 'data-id="trip"' in html
