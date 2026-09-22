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
import time
from datetime import timedelta

import pytest

from backend import app as app_module
from backend.app import app

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _no_real_refresh(monkeypatch):
    """ברירת מחדל: הרענון לא זמין, ובאופן לא-קטלני.

    בלי זה כל בקשה בקובץ הזה פנתה ל-GoTrue האמיתי עם טוקן מזויף —
    קריאת רשת אמיתית לייצור, בתוך בדיקה שמסומנת ‎unit‎. בדיקה שבודקת
    התנהגות רענון ספציפית דורסת את זה בעצמה."""
    monkeypatch.setattr(app_module.db, "refresh_session",
                        lambda _t: (None, "unit test", False))
    monkeypatch.setattr(app_module.db, "set_auth_token", lambda _t: None)


# ─── הגדרות העוגייה ──────────────────────────────────────────────────────────

def test_an_active_session_is_not_interrupted():
    """המספר הזה חל רק על סשן **נטוש**: משתמש פעיל דוחף את התפוגה קדימה
    בכל בקשה (הבדיקה הבאה), אז 90 יום לא מנתקים אף אחד שמשתמש.

    עשר שנים פירושן שמכשיר שנמכר, טלפון שאבד או דפדפן במחשב משותף
    נשארים מחוברים לנצח — ולמשתמש אין שום פעולה שסוגרת אותם."""
    assert app.permanent_session_lifetime >= timedelta(days=30), \
        "קצר מדי — מי שנכנס פעם בחודש ייזרק"
    assert app.permanent_session_lifetime <= timedelta(days=180), \
        "ארוך מדי — סשן נטוש לא נסגר בשום שלב"


def test_changing_the_password_disconnects_other_devices():
    """בלי זה שינוי סיסמה לא עשה כלום למי שכבר מחובר: הסשן מתחדש
    מעצמו, וטוקן הרענון ממשיך להחליף את עצמו."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent
           / "backend/supabase_config.py").read_text(encoding="utf-8")
    fn = src[src.index("def update_password("):]
    fn = fn[:fn.index("\ndef ")]

    assert "auth/v1/logout" in fn, "שינוי סיסמה לא מנתק שום מכשיר אחר"
    assert '"scope": "others"' in fn, \
        "ניתוק גלובלי היה מנתק גם את מי שביצע את השינוי"


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

    client_with_expiring_token.get("/__test/noop")

    with client_with_expiring_token.session_transaction() as sess:
        assert sess.get("user_id"), "בליפ רשת ניתק את המשתמש"


def test_a_rejected_refresh_token_does_sign_the_user_out(client_with_expiring_token, monkeypatch):
    """בקרת-נגד: כשהטוקן נדחה באמת אין מה לשחזר, וניתוק נקי הוא הנכון."""
    monkeypatch.setattr(app_module.db, "refresh_session",
                        lambda _t: (None, "Invalid Refresh Token", True))

    client_with_expiring_token.get("/__test/noop")

    with client_with_expiring_token.session_transaction() as sess:
        assert not sess.get("user_id")


def test_a_rejection_while_the_access_token_still_works_does_not_sign_out(monkeypatch):
    """מרוץ הסיבוב של Supabase: שני workers, שתי בקשות מקבילות, ו-refresh
    token שמסובב בכל רענון. הבקשה שמגיעה שנייה מקבלת "כבר נעשה בו שימוש"
    למרות שההתחברות חיה לגמרי — הרענון פשוט נעשה כבר על ידי האחרת.

    מה שמבדיל בין דחייה אמיתית לתוצאה של המרוץ הוא טוקן הגישה: כל עוד הוא
    בתוקף, יש במה להמשיך להשתמש והבקשה הבאה תנסה לרענן שוב."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]          = "00000000-0000-0000-0000-000000000000"
            sess["access_token"]     = "still-valid"
            sess["refresh_token"]    = "already-rotated-by-the-other-worker"
            # בתוך חלון הרענון המוקדם (120 שניות) אבל עוד לא פג
            sess["token_expires_at"] = time.time() + 60

        monkeypatch.setattr(app_module.db, "refresh_session",
                            lambda _t: (None, "Invalid Refresh Token: Already Used", True))

        response = c.get("/__test/noop")

        with c.session_transaction() as sess:
            assert sess.get("user_id"), "מרוץ סיבוב טוקנים ניתק את המשתמש"

        # ולא פחות חשוב: הבקשה הכושלת לא כותבת עוגייה. אילו כתבה, היא
        # הייתה דורסת את הטוקן החדש והתקין שהבקשה האחרת כבר שמרה.
        assert not any(h[0] == "Set-Cookie" and h[1].startswith("session=")
                       for h in response.headers), "בקשה כושלת דרסה את עוגיית ה-session"


def _noop_view():
    """עמוד מאומת שלא נוגע במסד.

    הבדיקות כאן בודקות עוגיות וטוקנים, לא נתונים. הן השתמשו ב-/settings
    כעמוד נוח, וזה קשר אותן במקרה לשליפות אמיתיות — מאז שכישלון שליפה
    נזרק במקום להיבלע (ראו DataUnavailable), העמוד הזה נכשל בגלוי עם
    טוקן מזויף, וזה הצית כישלונות בבדיקות שאין להן קשר לנושא."""
    return "ok"


app.add_url_rule("/__test/noop", "test_noop", _noop_view)


def _session_writing_view():
    """עמוד שכותב ל-session תוך כדי טיפול בבקשה, כמו שהדשבורד עושה עם
    recurring_synced. קיים כדי לבדוק שהקפאת העוגייה עומדת גם מולו."""
    from flask import session as flask_session
    flask_session["touched_by_the_view"] = "1"
    return "ok"


app.add_url_rule("/__test/session-writer", "test_session_writer", _session_writing_view)


def test_freezing_the_cookie_survives_a_view_that_writes_to_the_session(
        client_with_expiring_token, monkeypatch):
    """מלכודת: ביטול הכתיבה נעשה אחרי ה-view דווקא. אילו נעשה לפניו, כתיבה
    כלשהי ל-session בתוך ה-view הייתה מחזירה את הכתיבה לחיים — והעוגייה
    שהייתה נכתבת כבר לא הייתה קבועה, כלומר נמחקת בסגירת הדפדפן. זה בדיוק
    הניתוק שהמנגנון הזה אמור למנוע."""
    monkeypatch.setattr(app_module.db, "refresh_session",
                        lambda _t: (None, "temporary failure", False))

    response = client_with_expiring_token.get("/__test/session-writer")

    session_cookies = [h[1] for h in response.headers
                       if h[0] == "Set-Cookie" and h[1].startswith("session=")]
    assert not session_cookies, f"העוגייה נכתבה בכל זאת: {session_cookies}"


def test_a_network_blip_does_not_overwrite_the_cookie(client_with_expiring_token, monkeypatch):
    """אותו נימוק, בתקלה זמנית: אין לנו מה לשמור, אז לא נוגעים בעוגייה."""
    monkeypatch.setattr(app_module.db, "refresh_session",
                        lambda _t: (None, "temporary failure", False))

    response = client_with_expiring_token.get("/__test/noop")

    assert not any(h[0] == "Set-Cookie" and h[1].startswith("session=")
                   for h in response.headers)


def test_a_successful_refresh_stores_the_rotated_token(client_with_expiring_token, monkeypatch):
    """Supabase מסובב את ה-refresh token בכל רענון. אם לא נשמור את החדש,
    הרענון הבא ייכשל והמשתמש ינותק אחרי כשעה."""
    monkeypatch.setattr(app_module.db, "refresh_session",
                        lambda _t: (_FakeResponse(), None, False))

    client_with_expiring_token.get("/__test/noop")

    with client_with_expiring_token.session_transaction() as sess:
        assert sess["access_token"]  == "fresh-access"
        assert sess["refresh_token"] == "fresh-refresh"
        assert sess["user_id"]


# ─── יציאה יזומה ─────────────────────────────────────────────────────────────

def test_logging_out_really_ends_the_session(client_with_expiring_token):
    """היציאה היזומה היא הדרך היחידה החוצה, אז היא חייבת לעבוד."""
    client_with_expiring_token.post("/logout")

    with client_with_expiring_token.session_transaction() as sess:
        assert not sess.get("user_id")
        assert not sess.get("refresh_token")


def test_logging_out_works_even_while_a_refresh_is_failing(
        client_with_expiring_token, monkeypatch):
    """המלכודת של הקפאת העוגייה, בכיוון ההפוך.

    ההקפאה נועדה לא לדרוס טוקן תקין בטוקן מת כשרענון נכשל. אבל היא חלה
    על התגובה כולה — כולל על התגובה של /logout. מי שלחץ "התנתק" בדיוק
    כשהרענון נכשל קיבל הודעה שיצא, ראה את עוגיות המכשיר נמחקות, ונשאר
    מחובר לגמרי: עוגיית ה-session שלו מעולם לא נגעה, והבקשה הבאה
    החזירה אותו לאפליקציה.

    יציאה יזומה היא הדרך היחידה החוצה, אז היא חייבת לנצח כל אופטימיזציה."""
    monkeypatch.setattr(app_module.db, "refresh_session",
                        lambda _t: (None, "temporary failure", False))

    # POST ולא GET: ‎<img src=".../logout">‎ באתר אחר הוציא מבקר
    # מהחשבון שלו, כי ‎SameSite=Lax‎ שולח עוגייה בניווט GET.
    response = client_with_expiring_token.post("/logout")

    cleared = [h[1] for h in response.headers
               if h[0] == "Set-Cookie" and h[1].startswith("session=")]
    assert cleared, "עוגיית ה-session לא נמחקה — המשתמש נשאר מחובר"
    assert "1970" in cleared[0]

    with client_with_expiring_token.session_transaction() as sess:
        assert not sess.get("user_id")


# ─── זיכרון המכשיר: לא חוזרים לדף השיווק ─────────────────────────────────────
#
# דף הנחיתה נועד למי שלא מכיר את האפליקציה. מי שכבר התחבר מהמכשיר הזה אמור
# להגיע לאפליקציה, ואם ה-session נגמר — לטופס ההתחברות, לא לדף שיווק.

@pytest.fixture
def guest():
    app.config["TESTING"] = True
    return app.test_client()


def test_signing_in_marks_the_device_as_known(guest, monkeypatch):
    """נקודת הכניסה של כל המנגנון: בלי זה שום דבר אחר לא מופעל אף פעם."""
    class _Session:
        access_token, refresh_token, expires_at = "a", "r", 9999999999

    class _User:
        id, email = "00000000-0000-0000-0000-000000000000", "dana@example.com"

    class _SignIn:
        session, user = _Session(), _User()

    monkeypatch.setattr(app_module.db, "sign_in",        lambda e, p: (_SignIn(), None))
    monkeypatch.setattr(app_module.db, "set_auth_token", lambda t: None)
    monkeypatch.setattr(app_module.db, "log_login_event", lambda: None)
    # fetch_profile ולא get_profile: מסלול ההתחברות צריך לדעת אם השליפה
    # *נכשלה*, ולא רק מה היא החזירה — ראו tests/test_profile_read_failure.py
    monkeypatch.setattr(app_module.db, "fetch_profile",
                        lambda uid: ({"name": "דנה", "avatar_initial": "ד",
                                      "family_id": "11111111-1111-1111-1111-111111111111"}, True))

    response = guest.post("/login", data={"identifier": "dana@example.com",
                                          "password": "whatever"})

    cookies = [h[1] for h in response.headers if h[0] == "Set-Cookie"]
    assert any(c.startswith("sf_returning=1") for c in cookies)
    assert any(c.startswith("sf_last_id=dana%40example.com") or
               c.startswith("sf_last_id=dana@example.com") for c in cookies)
    # המזהה יושב על המכשיר, ולכן HttpOnly — ל-JS אין בו שימוש, ו-XSS
    # לא אמור לקרוא ממנו כתובת מייל.
    assert all("HttpOnly" in c for c in cookies if c.startswith("sf_"))


def test_a_first_time_visitor_gets_the_landing_page(guest):
    response = guest.get("/")

    assert response.status_code == 200
    assert "lp-hero" in response.get_data(as_text=True)


def test_a_known_device_skips_the_landing_page(guest):
    """הלב של הבקשה: מכשיר שכבר התחבר פעם לא רואה שוב את דף השיווק."""
    guest.set_cookie("sf_returning", "1")

    response = guest.get("/")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_the_landing_page_stays_reachable_on_purpose(guest):
    """כפתור "חזרה" שבטופס ההתחברות מצביע לכאן. בלי המילוט הזה הוא היה
    מחזיר את המכשיר המוכר ל-/login, כלומר לולאה."""
    guest.set_cookie("sf_returning", "1")

    response = guest.get("/?intro=1")

    assert response.status_code == 200
    assert "lp-hero" in response.get_data(as_text=True)


def test_the_router_is_never_cached(guest):
    """התשובה בשורש נגזרת מהעוגיות. תשובה שמורה פירושה דף שיווק למשתמש
    מחובר, או להפך."""
    for path in ("/", "/login"):
        response = guest.get(path)
        assert response.headers.get("Cache-Control") == "no-store", path
        assert "Cookie" in response.headers.get("Vary", ""), path


def test_the_login_form_remembers_who_you_are(guest):
    guest.set_cookie("sf_last_id", "someone@example.com")

    body = guest.get("/login").get_data(as_text=True)

    assert 'value="someone@example.com"' in body


def test_logging_out_brings_you_back_to_the_landing_page(client_with_expiring_token):
    """יציאה יזומה מאפסת הכול. היא הדרך היחידה החוצה, ומי שבוחר בה מקבל
    בדיוק את מה שאורח מקבל: דף הנחיתה, ומשם כפתור התחברות.

    זה גם מה שנותן משמעות לסימון המכשיר — אחרי היציאה הוא נמחק, ולכן
    מכשיר מסומן בלי session הוא בהכרח מקרה שבו ההתחברות נגמרה מעצמה."""
    response = client_with_expiring_token.post("/logout")

    assert response.headers["Location"].endswith("/")

    cookies = [h[1] for h in response.headers if h[0] == "Set-Cookie"]
    for name in ("sf_last_id", "sf_returning"):
        assert any(c.startswith(f"{name}=") and "Expires=Thu, 01 Jan 1970" in c
                   for c in cookies), f"{name} לא נמחקה ביציאה"

    # והמבחן האמיתי: הבקשה הבאה באמת מקבלת את דף הנחיתה
    landed = client_with_expiring_token.get("/")
    assert landed.status_code == 200
    assert "lp-hero" in landed.get_data(as_text=True)
