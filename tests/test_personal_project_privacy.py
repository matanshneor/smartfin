"""פרויקט אישי: מה שבו לא נראה ולא נגיש לשאר המשפחה.

בכל רשימה עסקאות של פרויקט אישי של אחר כבר היו מוסתרות — חוץ מרשימת
העסקאות הקבועות, שהציגה אותן בהגדרות ובעמוד החודש עם המזהה שלהן. ומהמזהה,
חמשת המסלולים שפועלים על עסקה לפי מזהה נתנו לערוך, למחוק, לפתוח קבלה,
לעצור סדרה ולפצל אותה: הם בדקו רק את פרויקט *היעד*.

RLS לא עוזרת כאן — היא מפרידה בין משפחות, וזו פרטיות בתוך משפחה.
"""
import pytest

from backend import app as app_module
from backend import supabase_config as db
from backend.app import app, limiter

from tests._fake_db import FakeSupabase

pytestmark = pytest.mark.unit

_FAM   = "11111111-1111-1111-1111-111111111111"
_ME    = "22222222-2222-2222-2222-222222222222"
_OTHER = "33333333-3333-3333-3333-333333333333"
_TX    = "44444444-4444-4444-4444-444444444444"

# כל מסלול שפועל על עסקה לפי מזהה, עם הפונקציה שהוא היה מגיע אליה
_ROUTES = [
    ("put",    f"/api/transactions/{_TX}",       {"amount": 1, "type": "expense", "date": "2026-09-01"},
     "update_transaction"),
    ("delete", f"/api/transactions/{_TX}?mode=one", None, "recurring_occurrence"),
    ("get",    f"/receipts/{_TX}",               None, "get_transaction_receipt_path"),
    ("delete", f"/api/recurring/{_TX}",          None, "stop_recurring"),
    ("put",    f"/api/recurring/{_TX}/sync",     {"instance_id": _TX}, "split_recurring_series"),
]


@pytest.fixture
def client(monkeypatch):
    limiter.reset()
    # עמוד השגיאה של הקבלה טוען את פרטי המשפחה — כמו ב-test_receipt_viewing
    monkeypatch.setattr(db, "set_auth_token", lambda t: None)
    monkeypatch.setattr(db, "get_family", lambda *a, **k: {})
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = _ME
            sess["family_id"] = _FAM
        yield c


def _call(client, method, url, body):
    return getattr(client, method)(url, json=body) if body is not None \
        else getattr(client, method)(url)


@pytest.mark.parametrize("method,url,body,reaches", _ROUTES,
                         ids=[r[3] for r in _ROUTES])
def test_someone_elses_personal_project_is_not_found(client, monkeypatch,
                                                     method, url, body, reaches):
    monkeypatch.setattr(db, "personal_project_owner", lambda tx, fam: _OTHER)
    monkeypatch.setattr(db, reaches,
                        lambda *a, **k: pytest.fail(f"הגיע ל-{reaches} על עסקה של אחר"))

    response = _call(client, method, url, body)

    assert response.status_code == 404


@pytest.mark.parametrize("owner", [_ME, None], ids=["my-own-project", "family-transaction"])
def test_my_own_and_family_transactions_still_work(client, monkeypatch, owner):
    """בקרת-נגד: בלעדיה הבדיקה שלמעלה עוברת גם כשהמסלול חוסם את כולם."""
    monkeypatch.setattr(db, "personal_project_owner", lambda tx, fam: owner)
    monkeypatch.setattr(db, "stop_recurring", lambda tid, fam: (True, None))

    response = client.delete(f"/api/recurring/{_TX}")

    assert response.status_code == 200


def test_a_failed_check_refuses_rather_than_allows(client, monkeypatch):
    """"לא הצלחתי לבדוק" אינו "מותר"."""
    def broken(*a):
        raise db.DataUnavailable("down")
    monkeypatch.setattr(db, "personal_project_owner", broken)
    monkeypatch.setattr(db, "stop_recurring",
                        lambda *a: pytest.fail("עבר למרות שהבדיקה נכשלה"))

    response = client.delete(f"/api/recurring/{_TX}")

    assert response.status_code == 503


# ─── הבדיקה עצמה ─────────────────────────────────────────────────────────────

def _fake_with(monkeypatch, rows):
    fake = FakeSupabase(transactions=rows)
    monkeypatch.setattr(db, "get_client", lambda: fake)
    return fake


def test_the_owner_is_read_from_the_transactions_project(monkeypatch):
    _fake_with(monkeypatch, [
        {"id": _TX, "family_id": _FAM, "project_id": "p", "projects": {"owner_id": _OTHER}},
    ])

    assert db.personal_project_owner(_TX, _FAM) == _OTHER


@pytest.mark.parametrize("row", [
    {"id": _TX, "family_id": _FAM, "project_id": None, "projects": None},
    {"id": _TX, "family_id": _FAM, "project_id": "p", "projects": {"owner_id": None}},
], ids=["household", "shared-project"])
def test_household_and_shared_transactions_have_no_owner(monkeypatch, row):
    _fake_with(monkeypatch, [row])

    assert db.personal_project_owner(_TX, _FAM) is None


def test_a_malformed_id_is_not_sent_to_the_database(monkeypatch):
    """PostgREST דוחה מזהה שאינו UUID בשגיאה, וזו הייתה הופכת ל-503."""
    fake = _fake_with(monkeypatch, [])

    assert db.personal_project_owner("not-a-uuid", _FAM) is None
    assert fake.reads == []


# ─── הרשימות ────────────────────────────────────────────────────────────────

def _template(tx_id, owner, project_id="p"):
    return {"id": tx_id, "family_id": _FAM, "is_recurring": True, "amount": 100.0,
            "type": "expense", "date": "2026-01-01", "description": "",
            "user_id": None, "category_id": None, "project_id": project_id,
            "recurring_frequency": "monthly_1", "recurring_end_date": None,
            "categories": None, "project_categories": None, "profiles": None,
            "projects": {"owner_id": owner} if project_id else None}


def test_the_recurring_list_hides_someone_elses_personal_project(monkeypatch):
    _fake_with(monkeypatch, [
        _template("theirs", _OTHER),
        _template("mine", _ME),
        _template("shared", None),
        _template("household", None, project_id=None),
    ])

    ids = {r["id"] for r in db.get_recurring_transactions(_FAM, _ME)}

    assert ids == {"mine", "shared", "household"}
