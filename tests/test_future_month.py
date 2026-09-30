"""חודש שעוד לא הגיע (מתן, 30.9 — רעיון 6).

נראה כמו כל חודש, עם מה שידוע עד כה: מה שהוזן אליו מראש, ועוד מופעי
העסקאות הקבועות שייפלו בו — בתאריכים שבהם ייפלו בפועל. הם נספרים במאזן
החודשי ובפילוחים, אבל אינם עסקאות אמיתיות, ולכן אין להם מזהה ללחיצה.
"""
import datetime

import pytest

from backend import app as app_module
from backend import supabase_config as db
from backend.app import app
from tests._fake_db import FakeSupabase

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"
_ME  = "22222222-2222-2222-2222-222222222222"
_TODAY = datetime.date(2026, 9, 30)


def _template(id_, amount, date, freq="monthly_1", type_="expense", end=None, project=None,
              name="שכר דירה", icon="🏠"):
    return {"id": id_, "family_id": _FAM, "amount": amount, "type": type_, "date": date,
            "description": name, "user_id": None, "category_id": "c1", "project_id": project,
            "project_category_id": None, "is_recurring": True, "recurring_parent_id": None,
            "recurring_frequency": freq, "recurring_end_date": end, "receipt_path": "r/1.jpg",
            "workplace": None, "categories": {"name": name, "icon": icon},
            "project_categories": None, "profiles": None, "projects": None}


def _projected(templates, year=2026, month=11):
    import unittest.mock as m
    with m.patch.object(db, "get_client", lambda: FakeSupabase(transactions=templates)):
        return db.projected_month_rows(_FAM, year, month, today=_TODAY)


def test_each_template_lands_on_its_real_dates_in_that_month():
    rows = _projected([_template("rent", 5500, "2026-01-01"),
                       _template("gan", 300, "2026-09-03", freq="weekly", name="גן")])

    got = sorted((r["recurring_parent_id"], r["date"]) for r in rows)
    assert got == [("gan", "2026-11-05"), ("gan", "2026-11-12"), ("gan", "2026-11-19"),
                   ("gan", "2026-11-26"), ("rent", "2026-11-01")]
    rent = next(r for r in rows if r["recurring_parent_id"] == "rent")
    assert rent["amount"] == 5500 and rent["categories"]["name"] == "שכר דירה"
    # לא תבנית, בלי קבלה, ומסומן כצפוי
    assert rent["is_recurring"] is False and rent["receipt_path"] is None and rent["projected"]


def test_a_series_that_ends_before_the_month_is_not_there():
    rows = _projected([_template("gym", 200, "2026-01-01", end="2026-10-15")])

    assert rows == []


def test_the_current_and_past_months_get_nothing():
    """שם המופעים כבר נוצרו כעסקאות אמיתיות — אסור לספור אותם פעמיים."""
    def boom():
        raise AssertionError("שליפה לחודש שאינו עתידי")
    import unittest.mock as m
    with m.patch.object(db, "get_client", boom):
        assert db.projected_month_rows(_FAM, 2026, 9, today=_TODAY) == []
        assert db.projected_month_rows(_FAM, 2026, 3, today=_TODAY) == []


# ── העמוד ─────────────────────────────────────────────────────────────

@pytest.fixture
def future_page(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setattr(db, "set_auth_token", lambda t: None)
    monkeypatch.setattr(db, "materialize_recurring", lambda fid: (0, True))
    monkeypatch.setattr(db, "get_anomalies", lambda *a, **k: [])
    monkeypatch.setattr(db, "get_family", lambda *a, **k: {"id": _FAM})
    monkeypatch.setattr(app_module, "family_settings", lambda: dict(db.DEFAULT_FAMILY_SETTINGS))
    monkeypatch.setattr(app_module.clock, "now", lambda: datetime.datetime(2026, 9, 30, 12, 0))
    monkeypatch.setattr(app_module.clock, "today", lambda: _TODAY)

    def render(real_rows, templates):
        monkeypatch.setattr(db, "fetch_month_page", lambda fid, y, m: {
            "family": {"id": _FAM}, "settings": dict(db.DEFAULT_FAMILY_SETTINGS),
            "members": [{"id": _ME, "name": "מתן"}],
            "categories": [{"id": "c1", "name": "שכר דירה", "icon": "🏠", "type": "expense"}],
            "rows": real_rows, "archive": []})
        monkeypatch.setattr(db, "get_client", lambda: FakeSupabase(transactions=templates))
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["user_id"] = _ME
                sess["family_id"] = _FAM
            res = c.get("/month?year=2026&month=11")
            assert res.status_code == 200
            return res.get_data(as_text=True)
    return render


def test_a_future_month_looks_like_any_month_with_what_is_known(future_page):
    html = future_page([], [_template("rent", 5500, "2026-01-01")])

    assert "לא נרשמו עסקאות" not in html
    assert "מאזן החודש" in html
    assert "₪5,500" in html
    assert "01.11" in html


def test_projected_rows_cannot_be_opened_for_editing(future_page):
    """אין מאחוריהן עסקה במסד — לחיצה הייתה מחזירה "העסקה כבר נמחקה"."""
    html = future_page([], [_template("rent", 5500, "2026-01-01")])

    rows = [r for r in html.split('<li class="cat-tx-row')[1:]]
    assert rows, "אין שורות"
    for r in rows:
        head = r[:r.index(">")]
        assert 'data-id=""' in head and 'role="button"' not in head


def test_with_no_templates_an_empty_future_month_stays_empty(future_page):
    html = future_page([], [])

    assert "לא נרשמו עסקאות" in html


def test_projected_and_real_rows_are_in_one_date_order(future_page):
    real = [{**_template("trip", 1400, "2026-11-20", name="טיסה", icon="✈️"),
             "is_recurring": False, "recurring_frequency": None, "receipt_path": None}]
    html = future_page(real, [_template("rent", 5500, "2026-01-01"),
                              _template("phone", 120, "2026-01-15", freq="monthly_15", name="סלולר", icon="📱")])

    all_tx = html[html.index('id="txSearch"'):]
    assert all_tx.index("20.11") < all_tx.index("15.11") < all_tx.index("01.11")
    # העסקה האמיתית עדיין נפתחת לעריכה
    assert 'data-id="trip"' in all_tx
