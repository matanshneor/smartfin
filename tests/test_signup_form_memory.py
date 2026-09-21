"""
שני באגים במסך הכניסה, שניהם פוגעים במי שנרשם בפעם הראשונה.

**ב3 — הטופס נמחק.** כל שגיאת הרשמה מחקה את כל ששת השדות, כולל קוד
ההזמנה. מי שקיבל קוד בוואטסאפ והקליד סיסמה קצרה מדי נשאר בלי הקוד
ובלי הפרטים, וצריך לחזור לשיחה ולחפש. זה ההפך הגמור מצד ההתחברות,
שם יש הערה מפורשת על שימור המזהה "כדי שלא יצטרך להקליד שוב אחרי
טעות בסיסמה".

**ב4 — כל כשל נקרא "סיסמה שגויה".** ‎db.sign_in‎ תופסת כל חריגה
ומחזירה את הטקסט שלה, וכל התוצאות מופו להודעה אחת. המקרה שהופך את
זה ממטרד למלכודת: אם אימות מייל יופעל אי-פעם, כל משתמש חדש ננעל
לצמיתות — נרשם, מקבל "כעת ניתן להתחבר", ומקבל "סיסמה שגויה" לנצח.
"""
import pytest

from backend import app as app_module
from backend.app import app, limiter, _login_error

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fresh_limits():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def anon(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setattr(app_module.db, "get_email_by_phone", lambda p: None)
    return app.test_client()


_FORM = {
    "first_name": "ישראל", "last_name": "ישראלי",
    "email": "israel@example.com", "phone": "050-1234567",
    "invite_code": "K4F2QX",
    "password": "sixchars", "password_confirm": "sixchars",
}


def _signup(client, **over):
    form = dict(_FORM)
    form.update(over)
    return client.post("/signup", data=form).get_data(as_text=True)


# ─── ב3: מה שהוקלד חוזר ─────────────────────────────────────────────────────

@pytest.mark.parametrize("broken,why", [
    ({"email": "israel@gmail"},        "מייל בלי סיומת"),
    ({"phone": "1"},                   "טלפון פסול"),
    ({"password_confirm": "other123"}, "סיסמאות לא תואמות"),
    ({"password": "abc"},              "סיסמה קצרה"),
])
def test_a_failed_signup_keeps_what_was_typed(anon, monkeypatch, broken, why):
    monkeypatch.setattr(app_module.db, "sign_up",
                        lambda *a, **k: pytest.fail("לא אמור להגיע לשרת"))

    html = _signup(anon, **broken)

    # השדות שלא נגענו בהם חוזרים כמו שהוקלדו
    assert 'value="ישראל"' in html, why
    assert 'value="ישראלי"' in html, why
    for field, typed in broken.items():
        if field.startswith("password"):
            continue
        # וגם השדה השגוי חוזר — מתקנים אותו, לא מקלידים הכול מחדש
        assert f'value="{typed}"' in html, f"{why}: {field} לא חזר"


def test_the_invite_code_survives_too(anon, monkeypatch):
    """זה החמור מכולם: הקוד הגיע בוואטסאפ, ובלעדיו המשתמש פותח משפחה
    חדשה במקום להצטרף לקיימת — ומפצל את המשפחה לשתיים."""
    monkeypatch.setattr(app_module.db, "sign_up", lambda *a, **k: (None, "x"))

    html = _signup(anon, password="abc")

    assert 'value="K4F2QX"' in html


def test_an_existing_email_also_keeps_the_form(anon, monkeypatch):
    """השגיאה הזאת מגיעה מהשרת ולא מהוולידציה המקומית — מסלול אחר."""
    monkeypatch.setattr(app_module.db, "sign_up",
                        lambda *a, **k: (None, "User already registered"))

    html = _signup(anon)

    assert "האימייל כבר קיים" in html
    assert 'value="K4F2QX"' in html


def test_the_passwords_are_never_echoed_back(anon, monkeypatch):
    """בקרת-נגד: אין סיבה שסיסמה תשב ב-HTML של תשובה."""
    monkeypatch.setattr(app_module.db, "sign_up", lambda *a, **k: (None, "x"))

    html = _signup(anon, email="israel@gmail")

    assert "sixchars" not in html


def test_a_fresh_signup_page_is_empty(anon):
    """בקרת-נגד: מי שנכנס לראשונה לא אמור לראות שדות מלאים."""
    html = anon.get("/signup").get_data(as_text=True)

    assert 'value="ישראל"' not in html


def test_being_rate_limited_does_not_wipe_the_form_either(anon, monkeypatch):
    """מי שנחסם אחרי לחיצה כפולה נענש פעמיים: גם לא נרשם, וגם איבד
    את מה שהקליד."""
    monkeypatch.setattr(app_module.db, "sign_up", lambda *a, **k: (None, "x"))

    html = ""
    for _ in range(8):
        html = _signup(anon)
        if "יותר מדי ניסיונות" in html:
            break

    assert "יותר מדי ניסיונות" in html, "המגבלה לא נאכפה — הבדיקה לא בדקה כלום"
    assert 'value="K4F2QX"' in html


# ─── ב4: כשל התחברות אומר מה קרה ────────────────────────────────────────────

def test_an_unconfirmed_email_says_so():
    """המלכודת: אם אימות מייל יופעל, כל משתמש חדש ננעל לצמיתות — וגם
    "שכחתי סיסמה" לא יעזור, כי הסיסמה מעולם לא הייתה הבעיה."""
    msg = _login_error("Email not confirmed")

    assert "לא אומת" in msg
    assert "סיסמה" not in msg


def test_a_rate_limit_says_to_wait():
    assert "נסו שוב בעוד כמה דקות" in _login_error("Request rate limit reached")


def test_an_outage_is_not_blamed_on_the_user():
    for err in ("Database not configured", "Connection timeout"):
        assert "השירות אינו זמין" in _login_error(err), err


def test_a_genuinely_wrong_password_still_says_so():
    """בקרת-נגד, והחשובה כאן: זה הרוב המוחלט של המקרים, ואסור להפוך
    אותו למעורפל."""
    for err in ("Invalid login credentials", "not found", ""):
        assert _login_error(err) == "אימייל/טלפון או סיסמה שגויים", err


def test_the_wrong_password_message_does_not_hint_which_field_was_wrong():
    """בקרת-נגד אבטחתית: הודעה שמבחינה בין "אין משתמש כזה" ל"הסיסמה
    שגויה" מאשרת למי שמנחש אילו כתובות רשומות."""
    assert _login_error("not found") == _login_error("Invalid login credentials")
