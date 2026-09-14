"""
בדיקות להישארות מחוברים.

הדרישה: מי שהתחבר נשאר מחובר תמיד, אלא אם יצא ביוזמתו.

שני דברים יכולים לשבור את זה, ושניהם מכוסים כאן:
1. פקיעת העוגייה — היא חייבת להיות ארוכה, והחלון חייב לנוע קדימה עם כל
   שימוש, אחרת משתמש פעיל היה מנותק בסוף התקופה.
2. כישלון רענון הטוקן — טוקן הגישה של Supabase חי כשעה ומוחלף אוטומטית.
   קודם כל שגיאה ברענון ניקתה את ה-session, כך שבליפ רשת אחד היה מנתק.
   רק דחייה אמיתית של ה-refresh token מצדיקה ניתוק.
"""
from datetime import timedelta

import pytest

from backend import app as app_module
from backend.app import app

pytestmark = pytest.mark.unit


# ─── הגדרות העוגייה ──────────────────────────────────────────────────────────

def test_the_session_lasts_effectively_forever():
    assert app.permanent_session_lifetime >= timedelta(days=365 * 5)


def test_the_expiry_window_slides_with_every_request():
    """בלי זה גם חלון ארוך היה נגמר בסוף, בלי קשר לשימוש."""
    assert app.config["SESSION_REFRESH_EACH_REQUEST"] is True


def test_the_cookie_stays_hardened():
    """ההתמדה לא באה על חשבון ההקשחה — העוגייה נושאת טוקני Supabase."""
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


# ─── הבחנה בין תקלה זמנית לדחייה אמיתית ──────────────────────────────────────

class _FakeSession:
    access_token = "fresh-access"
    refresh_token = "fresh-refresh"
    expires_at = 9999999999


class _FakeResponse:
    session = _FakeSession()


@pytest.fixture
def client_with_expiring_token(monkeypatch):
    """לקוח מחובר שהטוקן שלו כבר פג, כך שכל בקשה מנסה לרענן."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]            = "00000000-0000-0000-0000-000000000000"
            sess["user_name"]          = "בדיקה"
            sess["family_id"]          = None
            sess["access_token"]       = "stale"
            sess["refresh_token"]      = "some-refresh-token"
            sess["token_expires_at"]   = 0        # פג מזמן
        yield c


def test_a_network_blip_does_not_sign_the_user_out(client_with_expiring_token, monkeypatch):
    """זה הלב: תקלה זמנית משאירה את המשתמש מחובר."""
    monkeypatch.setattr(app_module.db, "refresh_session",
                        lambda _t: (None, "temporary failure", False))

    client_with_expiring_token.get("/settings")

    with client_with_expiring_token.session_transaction() as sess:
        assert sess.get("user_id"), "בליפ רשת ניתק את המשתמש"


def test_a_rejected_refresh_token_does_sign_the_user_out(client_with_expiring_token, monkeypatch):
    """בקרת-נגד: כשהטוקן נדחה באמת אין מה לשחזר, וניתוק נקי הוא הנכון."""
    monkeypatch.setattr(app_module.db, "refresh_session",
                        lambda _t: (None, "Invalid Refresh Token", True))

    client_with_expiring_token.get("/settings")

    with client_with_expiring_token.session_transaction() as sess:
        assert not sess.get("user_id")


def test_a_successful_refresh_stores_the_rotated_token(client_with_expiring_token, monkeypatch):
    """Supabase מסובב את ה-refresh token בכל רענון. אם לא נשמור את החדש,
    הרענון הבא ייכשל והמשתמש ינותק אחרי כשעה."""
    monkeypatch.setattr(app_module.db, "refresh_session",
                        lambda _t: (_FakeResponse(), None, False))

    client_with_expiring_token.get("/settings")

    with client_with_expiring_token.session_transaction() as sess:
        assert sess["access_token"]  == "fresh-access"
        assert sess["refresh_token"] == "fresh-refresh"
        assert sess["user_id"]


# ─── יציאה יזומה ─────────────────────────────────────────────────────────────

def test_logging_out_really_ends_the_session(client_with_expiring_token):
    """היציאה היזומה היא הדרך היחידה החוצה, אז היא חייבת לעבוד."""
    client_with_expiring_token.get("/logout")

    with client_with_expiring_token.session_transaction() as sess:
        assert not sess.get("user_id")
        assert not sess.get("refresh_token")
