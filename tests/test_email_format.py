"""
כתובת מייל לא נבדקה בכלל.

לשני טפסי האימות יש ‎novalidate‎ — בכוונה, כדי שהשגיאות יהיו בעברית
ובעיצוב של האפליקציה ולא בועית דפדפן באנגלית — ובשרת לא נבדק דבר. אז
מי שהקליד ‎israel@gmial‎ או ‎israel@gmail‎ נרשם בהצלחה.

והוא לא גילה כלום באותו רגע. הוא גילה חודש אחר כך, כשניסה לאפס סיסמה
והקישור נשלח לכתובת שלא קיימת: אין לו מוצא, ואין באפליקציה שום מסלול
לתקן כתובת מייל. במסד יש כבר חשבון כזה מיולי 2026 — ‎notanemail@nodottld‎.
"""
import pytest

from backend import app as app_module
from backend.app import app, limiter, _looks_like_email

pytestmark = pytest.mark.unit


@pytest.fixture
def anon():
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture(autouse=True)
def _fresh_limits():
    """המונים של flask_limiter חיים בזיכרון התהליך ולא פגים בתוך ריצה
    אחת — בלי איפוס, בדיקה כאן שורפת את המכסה של בדיקה בקובץ אחר."""
    limiter.reset()
    yield
    limiter.reset()


def _signup(client, email, **extra):
    form = {
        "first_name": "ישראל", "last_name": "ישראלי",
        "email": email, "phone": "050-1234567",
        "password": "sixchars", "password_confirm": "sixchars",
    }
    form.update(extra)
    return client.post("/signup", data=form)


# ─── הכתובת שבאמת נרשמה ─────────────────────────────────────────────────────

def test_the_address_that_actually_got_through_is_now_rejected(anon, monkeypatch):
    """‎notanemail@nodottld‎ — לא דוגמה מומצאת, אלא חשבון קיים במסד."""
    called = []
    monkeypatch.setattr(app_module.db, "sign_up",
                        lambda *a, **k: (called.append(a) or (None, "לא אמור להיקרא")))

    res = _signup(anon, "notanemail@nodottld")

    assert "כתובת המייל אינה תקינה" in res.get_data(as_text=True)
    assert called == [], "נוצר חשבון למרות כתובת פסולה"


def test_a_missing_suffix_is_rejected(anon, monkeypatch):
    """הטעות הנפוצה: להקליד ‎israel@gmail‎ ולשכוח את ‎.com‎."""
    monkeypatch.setattr(app_module.db, "sign_up",
                        lambda *a, **k: pytest.fail("נרשם עם כתובת בלי סיומת"))

    assert "כתובת המייל אינה תקינה" in _signup(anon, "israel@gmail").get_data(as_text=True)


def test_the_form_comes_back_with_the_signup_tab_open(anon):
    """בקרת-נגד: שגיאה שמחזירה את המשתמש לטאב ההתחברות נראית כאילו
    ההרשמה הצליחה."""
    html = _signup(anon, "israel@gmail").get_data(as_text=True)

    assert 'id="signupPanel"' in html
    assert "כתובת המייל אינה תקינה" in html


# ─── מה שחייב להמשיך לעבוד ──────────────────────────────────────────────────

def test_a_real_address_still_reaches_supabase(anon, monkeypatch):
    """בקרת-נגד, והחשובה ביותר כאן: בדיקה קפדנית מדי חוסמת הרשמות
    אמיתיות, וזה גרוע מהבאג."""
    seen = []
    monkeypatch.setattr(app_module.db, "sign_up",
                        lambda email, *a, **k: (seen.append(email) or (None, "stop")))

    _signup(anon, "israel@gmail.com")

    assert seen == ["israel@gmail.com"]


@pytest.mark.parametrize("email", [
    "israel@gmail.com",
    "first.last@company.co.il",      # תת-דומיין ישראלי, הנפוץ ביותר כאן
    "user+tag@gmail.com",            # תווית Gmail
    "user_name@my-domain.org",
    "UPPER@Example.COM",
    "a@b.co",
    "ישראל@gmail.com",               # חלק מקומי בעברית — חוקי
])
def test_valid_addresses_pass(email):
    assert _looks_like_email(email), f"{email} נדחתה בטעות"


@pytest.mark.parametrize("email", [
    "notanemail@nodottld",
    "israel@gmail",
    "israel",
    "@gmail.com",
    "israel@",
    "israel@.com",
    "israel@gmail..com",
    "israel@@gmail.com",
    "israel isra@gmail.com",         # רווח
    "a@b.c",                         # סיומת בת תו אחד לא קיימת
    "",
    "a@" + "b" * 250 + ".com",       # מעל 254 תווים
])
def test_invalid_addresses_fail(email):
    assert not _looks_like_email(email), f"{email} עברה בטעות"


# ─── "שכחתי סיסמה" ──────────────────────────────────────────────────────────

def test_a_broken_address_is_told_so_instead_of_pretending(anon, monkeypatch):
    """המסלול הזה עונה תמיד "נשלח", בכוונה, כדי לא לחשוף אילו כתובות
    רשומות. אבל פורמט פסול הוא לא מידע על מי רשום — ובלי הבדיקה, מי
    שהקליד כתובת שבורה חיכה לקישור שלא נשלח לשום מקום."""
    monkeypatch.setattr(app_module.db, "send_reset_email",
                        lambda *a, **k: pytest.fail("נשלח מייל לכתובת פסולה"))

    res = anon.post("/api/auth/forgot", json={"email": "israel@gmail"})

    assert res.status_code == 422
    assert res.get_json()["error"] == "כתובת המייל אינה תקינה"


def test_a_valid_address_still_gets_the_neutral_answer(anon, monkeypatch):
    """בקרת-נגד: הסודיות נשמרת — כתובת תקינה תמיד מקבלת "נשלח", בין אם
    היא רשומה ובין אם לא."""
    monkeypatch.setattr(app_module.db, "send_reset_email", lambda *a, **k: None)

    res = anon.post("/api/auth/forgot", json={"email": "nobody@example.com"})

    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}
