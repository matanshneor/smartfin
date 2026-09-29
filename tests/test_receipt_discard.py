"""מחיקת תמונה שנסרקה ולא נשמרה — ורק אותה.

הסריקה מעלה את התמונה לפני שיש עסקה. סריקה שננטשה השאירה קובץ יתום,
והניקוי הלילי שהיה אמור לאסוף אותו נכשל בכל ריצה. אז הדפדפן מבקש למחוק
ברגע הנטישה. הסכנה: דרך למחוק קבלה של עסקה קיימת, או של משפחה אחרת.
"""
import pytest

from backend import app as app_module
from backend import supabase_config as db
from backend.app import app, limiter

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"
_ME  = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def discard(monkeypatch):
    limiter.reset()
    app.config["TESTING"] = True
    deleted = []
    in_use = set()
    monkeypatch.setattr(db, "delete_receipt", lambda token, path: deleted.append(path))
    monkeypatch.setattr(db, "receipt_in_use", lambda path, fid: path in in_use)
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = _ME
            sess["family_id"] = _FAM
        yield (lambda path: c.post("/api/receipts/discard", json={"path": path})), deleted, in_use


def test_an_abandoned_scan_is_deleted(discard):
    post, deleted, _ = discard

    assert post(f"{_FAM}/abc.jpg").status_code == 200
    assert deleted == [f"{_FAM}/abc.jpg"]


def test_a_receipt_that_a_transaction_uses_is_not(discard):
    """אחרת זו דרך למחוק קבלה של עסקה קיימת — גם בשמירה שכבר הצליחה."""
    post, deleted, in_use = discard
    in_use.add(f"{_FAM}/kept.jpg")

    assert post(f"{_FAM}/kept.jpg").status_code == 409
    assert deleted == []


@pytest.mark.parametrize("path", [
    "99999999-9999-9999-9999-999999999999/x.jpg",     # משפחה אחרת
    f"{_FAM}/../99999999-9999-9999-9999-999999999999/x.jpg",
    "x.jpg", "", None, 5,
])
def test_only_this_familys_folder(discard, path):
    post, deleted, _ = discard

    assert post(path).status_code == 404
    assert deleted == []


def test_a_failed_check_deletes_nothing(discard, monkeypatch):
    """"לא יודע אם בשימוש" אינו "לא בשימוש"."""
    post, deleted, _ = discard
    def broken(*a):
        raise db.DataUnavailable("down")
    monkeypatch.setattr(db, "receipt_in_use", broken)

    assert post(f"{_FAM}/abc.jpg").status_code == 503
    assert deleted == []
