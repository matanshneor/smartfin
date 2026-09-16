"""
בדיקות לשבע הפונקציות שהחזירו ערך שקרי כשהשאילתה נכשלה.

התבנית: except → return 0 / [] / False / {}. הקורא לא יכול היה להבדיל
בין "אין נתונים" לבין "לא הצלחתי לבדוק", והתוצאה על המסך הייתה תשובה
בטוחה ושגויה. באג שנראה על המסך מקבל דיווח; זה לא — המשתמש מסתכל על
₪0 ומאמין שזה מה שיש.

הכלל שנבדק: כישלון שליפה נזרק ולא מומצא. במקומות שבהם תגובה מדודה
עדיפה על דף שגיאה, הכיוון הוא תמיד להחמיר ולא להקל.
"""
import pytest

from backend import app as app_module
from backend import supabase_config as db
from backend.app import app

pytestmark = pytest.mark.unit


class _BrokenClient:
    """כל שאילתה נכשלת, כמו בתקלת רשת חולפת."""
    def __getattr__(self, _n):
        def boom(*a, **k): raise RuntimeError("Supabase לא ענה")
        return boom


@pytest.fixture
def broken(monkeypatch):
    monkeypatch.setattr(db, "get_client", lambda: _BrokenClient())


# ─── כל שבע הפונקציות ────────────────────────────────────────────────────────

@pytest.mark.parametrize("call,what_it_used_to_return", [
    (lambda: db.get_monthly_summary("f", 2026, 9),  "₪0 לכל התקציב"),
    (lambda: db._fetch_categories("f"),             "רשימה ריקה → 'משפחה חדשה'"),
    (lambda: db.family_transaction_count("f"),      "0 → דילוג על אישור נטישה"),
    (lambda: db._fetch_family("f"),                 "{} → ברירות שיוך שגויות"),
    (lambda: db.family_has_no_transactions("f"),    "False"),
    (lambda: db.family_needs_onboarding("f"),       "False"),
    (lambda: db.receipt_scans_this_month("f"),      "0 → ההגבלה על OpenAI כבויה"),
])
def test_a_failed_query_raises_instead_of_inventing_an_answer(
        broken, call, what_it_used_to_return):
    with pytest.raises(db.DataUnavailable):
        call()


# ─── מה שהמשתמש רואה ─────────────────────────────────────────────────────────

def test_the_dashboard_does_not_show_a_zeroed_budget(broken):
    """התקרית מאוגוסט. עדיף דף שגיאה, שאפשר לרענן אחריו, על תקציב
    מאופס שנראה אמיתי."""
    app.config["TESTING"] = False
    try:
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["user_id"]   = "11111111-1111-1111-1111-111111111111"
                sess["family_id"] = "22222222-2222-2222-2222-222222222222"
            body = c.get("/").get_data(as_text=True)

        assert "₪0" not in body, "הדשבורד עדיין מציג תקציב מאופס בתקלה"
        assert "שגיאה" in body or "נסה שוב" in body
    finally:
        app.config["TESTING"] = True


# ─── בכישלון — מחמירים, לא מקלים ─────────────────────────────────────────────

def test_a_failed_quota_check_refuses_the_scan(broken, monkeypatch):
    """אישור סריקה כשהמכסה לא נבדקה מבטל בפועל את ההגבלה על ההוצאה."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]   = "11111111-1111-1111-1111-111111111111"
            sess["family_id"] = "22222222-2222-2222-2222-222222222222"

        response = c.post("/api/receipts/scan")

    assert response.status_code == 503, "הסריקה אושרה למרות שהמכסה לא נבדקה"


def test_a_failed_count_still_asks_before_abandoning_a_family(monkeypatch):
    """דילוג על האישור בגלל תקלה הוא בדיוק האובדן שהאישור מונע."""
    monkeypatch.setattr(app_module.db, "family_transaction_count",
                        lambda fid: (_ for _ in ()).throw(db.DataUnavailable("x")))
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]   = "11111111-1111-1111-1111-111111111111"
            sess["family_id"] = "22222222-2222-2222-2222-222222222222"

        response = c.post("/api/family/join", json={"code": "ABC123"})

    assert response.status_code == 409
    assert response.get_json()["needs_confirm"] is True


def test_the_confirmation_does_not_invent_a_number(monkeypatch):
    """הודעה שאומרת 'יש null תנועות' גרועה מהודעה בלי מספר."""
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent
          / "frontend/static/js/settings.js").read_text(encoding="utf-8")

    assert "typeof n === 'number'" in js
    assert "יש תנועות קיימות" in js


def test_the_error_page_itself_survives_a_dead_database(broken):
    """מלכודת שנחשפה תוך כדי: מעבד ההקשר שמזין הגדרות לכל תבנית רץ גם
    על error.html. בלי הגנה שם, תקלה במסד הפילה גם את דף השגיאה שנועד
    לדווח עליה — והמשתמש קיבל מסך ריק לגמרי במקום הודעה."""
    app.config["TESTING"] = False
    try:
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["user_id"]   = "11111111-1111-1111-1111-111111111111"
                sess["family_id"] = "22222222-2222-2222-2222-222222222222"
            response = c.get("/")

        assert response.status_code == 500
        assert "error-code" in response.get_data(as_text=True) or \
               "שגיאה" in response.get_data(as_text=True)
    finally:
        app.config["TESTING"] = True
