"""
שלושה חורים באותו קיר: מה נכנס למסד, ומה מדווח בחזרה.

· ‎/api/recurring/<id>/sync‎ היה המסלול הכותב **היחיד** שלא עבר
  ב-‎_parse_amount‎ ולא אימת קטגוריה. ‎float()‎ חשוף קיבל ‎-5000‎ ו-‎inf‎,
  שנעצרו רק ב-CHECK של המסד וחזרו למשתמש כ-500 סתום.

· ‎date‎ עבר מגוף הבקשה למסד בלי שום בדיקה, ולעמודה לא היה אילוץ. עם
  מנוע העסקאות הקבועות זה לא תיאורטי: תאריך התחלה בשנת 1000 מייצר
  מופע לכל חודש מאז, עד תקרת 500 השורות, בקריאה אחת.

· ‎update_transaction‎ ו-‎delete_transaction‎ לא בדקו כמה שורות הושפעו.
  עריכה של עסקה שבן משפחה אחר מחק לפני שנייה החזירה "נשמר".
"""
import pytest

from backend import app as app_module
from backend import supabase_config as db
from backend.app import app, _parse_date

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"
_TX  = "22222222-2222-2222-2222-222222222222"
_CAT = "44444444-4444-4444-4444-444444444444"


@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setattr(app_module.db, "get_categories",
                        lambda *a, **k: [{"id": _CAT, "name": "מכולת", "type": "expense"}])
    monkeypatch.setattr(app_module, "family_settings",
                        lambda: dict(db.DEFAULT_FAMILY_SETTINGS))
    monkeypatch.setattr(app_module.db, "is_recurring_instance", lambda *a: False)
    monkeypatch.setattr(app_module.db, "materialize_recurring", lambda fam: (0, True))
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]   = "33333333-3333-3333-3333-333333333333"
            sess["family_id"] = _FAM
        yield c


def _add(client, confirm=False, **over):
    body = {"amount": 100, "type": "expense", "date": "2026-09-21"}
    body.update(over)
    # ‎confirm‎ עוקף את שער המילוי-אחורה (ראו ‎_RETRO_WITHOUT_CONFIRM‎).
    # סדרה שמתחילה חודשים אחורה מייצרת שורות אמיתיות, ולכן נשאלת שאלה.
    url = "/api/transactions" + ("?confirm=1" if confirm else "")
    return client.post(url, json=body)


# ─── תאריך ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,why", [
    ("1000-01-01",  "שנת 1000 — 500 שורות בקריאה אחת"),
    ("9999-12-31",  "עתיד רחוק"),
    ("2026-13-01",  "חודש 13"),
    ("2026-02-30",  "30 בפברואר"),
    ("לא תאריך",    "טקסט"),
    ("",            "ריק"),
])
def test_an_impossible_date_never_reaches_the_database(client, monkeypatch, raw, why):
    monkeypatch.setattr(app_module.db, "add_transaction",
                        lambda *a, **k: pytest.fail(f"נכתב תאריך פסול: {why}"))

    assert _add(client, date=raw).status_code == 422, why


def test_ordinary_dates_still_pass():
    """בקרת-נגד, והחשובה כאן: בדיקה קפדנית מדי חוסמת הזנת היסטוריה."""
    from backend import clock
    y = clock.today().year
    for raw in (f"{y}-01-01", f"{y - 3}-06-15", f"{y + 1}-12-31"):
        assert _parse_date(raw) == (raw, None), raw


def test_a_series_cannot_end_before_it_starts(client, monkeypatch):
    """"עסקה קבועה" שנגמרה לפני שהתחילה לא תייצר אף מופע, והמשתמש
    מאמין שהיא פעילה."""
    monkeypatch.setattr(app_module.db, "add_transaction",
                        lambda *a, **k: pytest.fail("נשמרה סדרה שנגמרת לפני שהתחילה"))

    res = _add(client, date="2026-05-01", is_recurring=True,
               recurring_frequency="monthly_1", recurring_end_date="2026-01-01")

    assert res.status_code == 422
    assert "מוקדם מתאריך ההתחלה" in res.get_json()["error"]


def test_a_valid_end_date_is_accepted(client, monkeypatch):
    saved = {}
    monkeypatch.setattr(app_module.db, "add_transaction",
                        lambda payload, **k: (saved.update(payload) or ({"id": _TX}, None)))

    res = _add(client, confirm=True, date="2026-05-01", is_recurring=True,
               recurring_frequency="monthly_1", recurring_end_date="2027-05-01")

    assert res.status_code == 201
    assert saved["recurring_end_date"] == "2027-05-01"


def test_the_database_itself_refuses_an_absurd_date():
    """הרשת האחרונה, לכל מי שעוקף את פייתון. אומת מול המסד החי:
    שנת 1000 נחסמה, סיום-לפני-התחלה נחסם, ותאריך תקין עבר."""
    from pathlib import Path
    sql = (Path(__file__).resolve().parent.parent
           / "backend/supabase/migrations/20260921200000_transaction_date_bounds.sql"
           ).read_text(encoding="utf-8")

    assert "transactions_date_sane" in sql
    assert "transactions_recurring_end_after_start" in sql


# ─── מסלול הסנכרון ──────────────────────────────────────────────────────────

def _sync(client, **body):
    return client.put(f"/api/recurring/{_TX}/sync", json=body)


@pytest.mark.parametrize("amount", [-5000, 0, "abc", 1e400, 999_999_999])
def test_the_sync_route_now_validates_the_amount(client, monkeypatch, amount):
    monkeypatch.setattr(app_module.db, "update_recurring_template",
                        lambda *a, **k: pytest.fail(f"נכתב סכום פסול: {amount}"))

    assert _sync(client, amount=amount).status_code == 422


def test_the_sync_route_now_validates_the_category(client, monkeypatch):
    """בלי זה תבנית יכלה להצביע על קטגוריה של משפחה אחרת, וכל מופע
    עתידי היה נוחת בדלי "אחר"."""
    monkeypatch.setattr(app_module.db, "transaction_type", lambda *a: "expense")
    monkeypatch.setattr(app_module.db, "update_recurring_template",
                        lambda *a, **k: pytest.fail("נכתבה קטגוריה זרה"))

    res = _sync(client, amount=100, category_id="99999999-9999-9999-9999-999999999999")

    assert res.status_code == 422
    assert res.get_json()["error"] == "הקטגוריה לא נמצאה"


def test_the_sync_route_still_works_for_a_valid_request(client, monkeypatch):
    """בקרת-נגד: זו התכונה — "שינית סכום, לעדכן גם את התבנית?"."""
    monkeypatch.setattr(app_module.db, "transaction_type", lambda *a: "expense")
    seen = {}
    monkeypatch.setattr(app_module.db, "update_recurring_template",
                        lambda tid, fam, **k: (seen.update(k) or ({"id": tid}, None)))

    res = _sync(client, amount=250, category_id=_CAT)

    assert res.status_code == 200
    assert seen["amount"] == 250
    assert seen["category_id"] == _CAT


# ─── כתיבה שלא נגעה בכלום ───────────────────────────────────────────────────

def test_editing_a_transaction_that_no_longer_exists_says_so(client, monkeypatch):
    """בן משפחה אחר מחק אותה לפני שנייה. עד היום זה חזר 200 "נשמר"."""
    monkeypatch.setattr(app_module.db, "update_transaction", lambda *a, **k: (None, None))

    res = client.put(f"/api/transactions/{_TX}", json={
        "amount": 100, "type": "expense", "date": "2026-09-21"})

    assert res.status_code == 404
    assert "ייתכן שנמחקה בינתיים" in res.get_json()["error"]


class _Deleted:
    """לקוח שמדווח כמה שורות באמת נמחקו."""

    def __init__(self, rows):
        self.rows = rows

    def table(self, _n):        return self
    def delete(self, *a, **k):  return self
    def eq(self, *a, **k):      return self

    def execute(self):
        self.data = self.rows
        return self


def test_deleting_a_row_that_matched_nothing_is_not_a_success(monkeypatch):
    monkeypatch.setattr(db, "get_client", lambda: _Deleted([]))

    assert db.delete_transaction(_TX, _FAM) is False


def test_deleting_a_row_that_did_match_is(monkeypatch):
    monkeypatch.setattr(db, "get_client", lambda: _Deleted([{"id": _TX}]))

    assert db.delete_transaction(_TX, _FAM) is True


def test_a_reset_reports_how_many_rows_it_removed(monkeypatch):
    """הפעולה ההרסנית ביותר באפליקציה החזירה ‎True‎ קבוע — גם כשלא
    נמחק כלום, וגם כשנמחקו מאות."""
    monkeypatch.setattr(db, "get_client", lambda: _Deleted([{"id": 1}, {"id": 2}, {"id": 3}]))

    assert db.reset_transactions(_FAM) == (3, None)


def test_an_empty_reset_is_not_an_error(monkeypatch):
    """בקרת-נגד: משפחה בלי עסקאות שמאפסת — אפס שורות זו תוצאה תקינה,
    לא כישלון."""
    monkeypatch.setattr(db, "get_client", lambda: _Deleted([]))

    assert db.reset_transactions(_FAM) == (0, None)
