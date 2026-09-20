"""
המסלול היחיד שעולה כסף — והיחיד בלי שום בלם.

‎/api/receipts/scan‎ קורא ל-OpenAI. המכסה הייתה 100 סריקות **לכל
משפחה**, וההרשמה פתוחה: כל חשבון חדש מקבל משפחה, ואיתה מכסה טרייה.
כלומר לא הייתה שום תקרה על הסכום הכולל. ומבין 23 המסלולים הכותבים
באפליקציה, זה היה היחיד בלי הגבלת קצב בכלל.

יש גם תקרת חיוב בלוח הבקרה של OpenAI, והיא רשת הביטחון האחרונה.
התקרה כאן קיימת כי היא נכשלת אחרת: בעברית, עם הצעה להזין ידנית, במקום
שהמפתח ייחסם ותתקבל שגיאת API סתומה שנראית למשתמש כמו באג.
"""
import io

import pytest

from backend import app as app_module
from backend.app import app, limiter

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def _fresh_limits():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setattr(app_module.db, "get_categories", lambda *a, **k: [])
    monkeypatch.setattr(app_module.db, "record_receipt_scan", lambda *a, **k: None)
    monkeypatch.setattr(app_module.db, "upload_receipt", lambda *a, **k: (None, None))
    # אותם מפתחות שהפונקציה האמיתית מבטיחה תמיד (ראו scan_receipt)
    monkeypatch.setattr(app_module.db, "scan_receipt", lambda *a, **k: (
        {"amount": 12.5, "merchant": "סופר", "date": "2026-09-20",
         "category_name": None}, None))
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]   = "22222222-2222-2222-2222-222222222222"
            sess["family_id"] = _FAM
        yield c


def _quota(monkeypatch, mine=0, everyone=0):
    monkeypatch.setattr(app_module.db, "receipt_scans_this_month", lambda *a: mine)
    monkeypatch.setattr(app_module.db, "receipt_scans_globally_this_month", lambda: everyone)


def _scan(client):
    return client.post("/api/receipts/scan", content_type="multipart/form-data",
                       data={"image": (io.BytesIO(b"\xff\xd8fake"), "r.jpg", "image/jpeg")})


# ─── התקרה הגלובלית ─────────────────────────────────────────────────────────

def test_the_service_stops_when_everyone_together_hits_the_ceiling(client, monkeypatch):
    """הלב: המשפחה הזאת ניצלה 0 מתוך 100 שלה, והסריקה בכל זאת נעצרת."""
    _quota(monkeypatch, mine=0, everyone=app_module.db.RECEIPT_GLOBAL_MONTHLY_LIMIT)

    res = _scan(client)

    assert res.status_code == 503
    assert "ניתן להזין את הפרטים ידנית" in res.get_json()["error"]


def test_the_message_does_not_blame_the_person_standing_there(client, monkeypatch):
    """הוא לא ניצל שום מכסה. הודעה על "המכסה שלכם" הייתה פשוט שקר."""
    _quota(monkeypatch, mine=0, everyone=99999)

    error = _scan(client).get_json()["error"]

    assert "מכסת הסריקות החודשית" not in error
    assert "הגעתם" not in error


def test_one_below_the_ceiling_still_works(client, monkeypatch):
    """בקרת-נגד: שגיאת גדר-אחת כאן משביתה את התכונה ליום שלם."""
    _quota(monkeypatch, mine=0, everyone=app_module.db.RECEIPT_GLOBAL_MONTHLY_LIMIT - 1)

    assert _scan(client).status_code == 200


def test_the_family_quota_still_applies_on_its_own(client, monkeypatch):
    _quota(monkeypatch, mine=app_module.db.RECEIPT_MONTHLY_LIMIT, everyone=1)

    res = _scan(client)

    assert res.status_code == 429
    assert "מכסת הסריקות החודשית" in res.get_json()["error"]


def test_a_failed_count_refuses_rather_than_guessing(client, monkeypatch):
    """אישור כשהבדיקה נכשלה מבטל בפועל את ההגבלה על ההוצאה."""
    def _boom():
        raise app_module.db.DataUnavailable("global")
    monkeypatch.setattr(app_module.db, "receipt_scans_this_month", lambda *a: 0)
    monkeypatch.setattr(app_module.db, "receipt_scans_globally_this_month", _boom)

    assert _scan(client).status_code == 503


def test_the_ceiling_can_be_raised_without_a_deploy(monkeypatch):
    """מספר שמצריך פריסה כדי לשנות אותו הוא מספר שיישאר שגוי בדיוק
    כשצריך לשנות אותו."""
    import importlib, os
    monkeypatch.setenv("RECEIPT_GLOBAL_MONTHLY_LIMIT", "12345")
    db = importlib.reload(app_module.db)
    try:
        assert db.RECEIPT_GLOBAL_MONTHLY_LIMIT == 12345
    finally:
        monkeypatch.delenv("RECEIPT_GLOBAL_MONTHLY_LIMIT")
        importlib.reload(db)


# ─── הגבלת קצב ──────────────────────────────────────────────────────────────

def test_the_expensive_route_is_rate_limited(client, monkeypatch):
    """23 מסלולים כותבים, וזה היה היחיד בלי הגבלה — דווקא היקר."""
    _quota(monkeypatch, mine=0, everyone=0)

    codes = [_scan(client).status_code for _ in range(12)]

    assert 429 in codes, "אין הגבלת קצב על סריקת קבלות"


def test_a_normal_person_never_meets_the_rate_limit(client, monkeypatch):
    """סריקה אחת לוקחת 2-6 שניות. מי שסורק שלוש קבלות ברצף הוא אדם,
    לא סקריפט, והוא לא אמור להיחסם."""
    _quota(monkeypatch, mine=0, everyone=0)

    assert [_scan(client).status_code for _ in range(3)] == [200, 200, 200]


# ─── שתי הספירות מתאפסות יחד ────────────────────────────────────────────────

def test_both_counts_share_one_month_boundary():
    """השרת רץ ב-UTC והחודש נמדד בשעון ישראל. שני גבולות שונים היו
    מאפסים את המכסות בשעות שונות."""
    from backend import supabase_config as db
    import inspect

    family = inspect.getsource(db.receipt_scans_this_month)
    glob   = inspect.getsource(db.receipt_scans_globally_this_month)

    assert "_month_start()" in family
    assert "_month_start()" in glob
