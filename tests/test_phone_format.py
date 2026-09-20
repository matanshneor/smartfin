"""
גם מספר הטלפון לא נבדק.

‎_normalize_phone‎ הסירה כל מה שאינו ספרה והחזירה את מה שנשאר, וזהו. אז
‎1‎ היה מספר טלפון תקין: הוא נשמר בפרופיל, הפך למזהה התחברות חלופי חסר
משמעות — ובגלל האינדקס הייחודי על השדה הוא גם חסם את הערך הזה לכל שאר
המשתמשים, לתמיד.

ובאג שני באותו מקום: קידומת ‎+972‎ נשמרה כמו שהיא. מי שנרשם עם
‎+972-54-1234567‎ נשמר כ-‎972541234567‎, ואז ניסה להתחבר עם
‎054-1234567‎ — ולא נמצא. שני אנשים גם יכלו "לתפוס" את אותו מספר, כל
אחד בכתיב אחר, בלי שהאינדקס הייחודי ירגיש.
"""
import pytest

from backend import app as app_module
from backend.app import app, limiter, _looks_like_phone, _normalize_phone

pytestmark = pytest.mark.unit


@pytest.fixture
def anon(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setattr(app_module.db, "sign_up",
                        lambda *a, **k: pytest.fail("נרשם עם טלפון פסול"))
    return app.test_client()


@pytest.fixture(autouse=True)
def _fresh_limits():
    limiter.reset()
    yield
    limiter.reset()


def _signup(client, phone):
    return client.post("/signup", data={
        "first_name": "ישראל", "last_name": "ישראלי",
        "email": "israel@example.com", "phone": phone,
        "password": "sixchars", "password_confirm": "sixchars",
    })


# ─── מה שנרשם היום ולא היה צריך ─────────────────────────────────────────────

@pytest.mark.parametrize("phone", ["1", "12345", "*6120", "0512345"])
def test_a_number_that_is_not_a_number_is_rejected(anon, phone):
    assert "מספר הטלפון אינו תקין" in _signup(anon, phone).get_data(as_text=True)


def test_a_foreign_number_is_rejected(anon):
    """הטלפון הוא מזהה התחברות ישראלי, ומספר זר לא יימצא בחיפוש לעולם."""
    assert "מספר הטלפון אינו תקין" in _signup(anon, "+1-555-123-4567").get_data(as_text=True)


@pytest.mark.parametrize("phone,why", [
    ("050123456",   "ספרה חסרה"),
    ("05012345678", "ספרה עודפת"),
])
def test_the_wrong_length_is_rejected(anon, phone, why):
    assert "מספר הטלפון אינו תקין" in _signup(anon, phone).get_data(as_text=True), why


# ─── מה שחייב להמשיך לעבוד ──────────────────────────────────────────────────

@pytest.mark.parametrize("phone", [
    "050-1234567",      # הכתיב שבתיבת ההזנה
    "0541234567",       # מספר אמיתי מהמסד
    "0509876543",       # מספר אמיתי מהמסד
    "03-1234567",       # קווי תל אביב
    "09-8765432",       # קווי שרון
    "04 987 6543",      # עם רווחים
    "077-1234567",      # 07X
])
def test_real_numbers_pass(phone):
    """בקרת-נגד, והחשובה כאן: בדיקה קפדנית מדי חוסמת הרשמות אמיתיות,
    וזה גרוע מהבאג. שני המספרים באמצע הם של החשבונות הקיימים."""
    assert _looks_like_phone(_normalize_phone(phone)), f"{phone} נדחה בטעות"


def test_a_valid_number_reaches_supabase(monkeypatch):
    app.config["TESTING"] = True
    limiter.reset()
    seen = []
    monkeypatch.setattr(app_module.db, "sign_up",
                        lambda e, p, n, phone=None: (seen.append(phone) or (None, "stop")))

    _signup(app.test_client(), "050-1234567")

    assert seen == ["0501234567"]


# ─── ‎+972‎ הוא אותו מספר ────────────────────────────────────────────────────

@pytest.mark.parametrize("written", ["+972-54-123-4567", "972541234567", "+972 54 1234567"])
def test_the_country_code_becomes_a_local_number(written):
    """הלב של הבאג השני: אותו מספר נשמר בשתי צורות, וההתחברות בצורה
    השנייה לא מצאה אותו."""
    assert _normalize_phone(written) == "0541234567"


def test_both_spellings_look_up_the_same_person(monkeypatch):
    """מה שקורה בפועל במסך ההתחברות."""
    asked = []
    monkeypatch.setattr(app_module.db, "get_email_by_phone",
                        lambda p: asked.append(p) or None)
    monkeypatch.setattr(app_module.db, "sign_in", lambda e, p: (None, "no"))
    app.config["TESTING"] = True
    limiter.reset()
    c = app.test_client()

    c.post("/login", data={"identifier": "054-1234567",      "password": "x"})
    c.post("/login", data={"identifier": "+972-54-1234567",  "password": "x"})

    assert asked == ["0541234567", "0541234567"], "אותו מספר נשאל בשתי צורות"


# ─── עריכת הפרופיל ──────────────────────────────────────────────────────────

def test_editing_a_profile_cannot_smuggle_a_bad_number(monkeypatch):
    """ההרשמה היא לא הדרך היחידה פנימה — הטלפון ניתן לעריכה אחר כך."""
    app.config["TESTING"] = True
    monkeypatch.setattr(app_module.db, "update_profile",
                        lambda *a, **k: pytest.fail("נשמר טלפון פסול"))
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"]   = "00000000-0000-0000-0000-000000000000"
        sess["family_id"] = None

    res = c.put("/api/profile", json={"first_name": "ישראל", "last_name": "ישראלי",
                                      "phone": "1"})

    assert res.status_code == 422
    assert res.get_json()["error"] == "מספר הטלפון אינו תקין — למשל 050-1234567"


def test_clearing_the_phone_in_the_profile_is_still_allowed(monkeypatch):
    """בקרת-נגד: בעריכה השדה אינו חובה, ובדיקה שמפילה ריק הייתה נועלת
    את כל מסך עריכת הפרטים למי שאין לו טלפון שמור."""
    app.config["TESTING"] = True
    saved = []
    monkeypatch.setattr(app_module.db, "get_profile", lambda *a, **k: {})
    monkeypatch.setattr(app_module.db, "update_profile",
                        lambda uid, name, phone, workplace: saved.append(phone) or (True, None))
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"]   = "00000000-0000-0000-0000-000000000000"
        sess["family_id"] = None

    res = c.put("/api/profile", json={"first_name": "ישראל", "last_name": "ישראלי",
                                      "phone": ""})

    assert res.status_code == 200
    assert saved == [None]
