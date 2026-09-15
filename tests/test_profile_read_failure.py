"""
בדיקות לכישלון חולף בשליפת הפרופיל בזמן התחברות.

זה היה הבאג ההרסני ביותר שהביקורת מצאה, והוא כולו נובע מהבדל אחד שלא
נעשה: get_profile החזיר None גם כש"אין פרופיל" וגם כש"השרת לא ענה".

השרשרת: תקלת רשת של שתי שניות בזמן התחברות ← get_profile מחזיר None ←
המסלול מסיק שאין family_id ← ensure_family מסיק שאין משפחה ← הוא יוצר
משפחה חדשה **ודורס את השיוך הקיים**. המשתמש נוחת על דשבורד ריק, וכל
העסקאות שלו נשארות מאחורי family_id ישן שאין אליו דרך חזרה מהממשק.
בן הזוג נשאר במשפחה הישנה, ומאותו רגע השניים מזינים לשני תקציבים
נפרדים בלי לדעת.

הכלל שנבדק כאן: לעולם לא להסיק "אין" מתוך "לא הצלחתי לבדוק".
"""
import pytest

from backend import app as app_module
from backend import supabase_config as db
from backend.app import app, limiter

pytestmark = pytest.mark.unit


class _Session:
    access_token, refresh_token, expires_at = "a", "r", 9999999999


class _User:
    id, email = "00000000-0000-0000-0000-000000000000", "dana@example.com"


class _SignIn:
    session, user = _Session(), _User()


@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    limiter.reset()
    monkeypatch.setattr(app_module.db, "sign_in",        lambda e, p: (_SignIn(), None))
    monkeypatch.setattr(app_module.db, "set_auth_token", lambda t: None)
    monkeypatch.setattr(app_module.db, "log_login_event", lambda: None)
    yield app.test_client()
    limiter.reset()


def _login(client):
    return client.post("/login", data={"identifier": "dana@example.com", "password": "x"})


# ─── ההבחנה עצמה ─────────────────────────────────────────────────────────────

def test_a_failed_read_is_not_reported_as_a_missing_profile(monkeypatch):
    """הלב. בלי ההבחנה הזאת כל שאר הבדיקות כאן לא יכולות לעבוד."""
    class _Boom:
        def table(self, *a, **k): raise RuntimeError("Supabase לא ענה")

    monkeypatch.setattr(db, "get_client", lambda: _Boom())
    profile, ok = db.fetch_profile("some-user")

    assert profile is None
    assert ok is False, "כישלון שליפה דווח כ'אין פרופיל'"


def test_a_genuinely_missing_profile_is_reported_as_an_answer(monkeypatch):
    """בקרת-נגד: 'אין שורה' הוא תשובה תקפה ולא תקלה, אחרת משתמש חדש
    לגמרי לעולם לא יקבל משפחה."""
    from postgrest.exceptions import APIError

    class _Empty:
        def table(self, *a, **k): return self
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def single(self, *a, **k): return self
        def execute(self):
            raise APIError({"code": "PGRST116", "details": "The result contains 0 rows",
                            "hint": None, "message": "..."})

    monkeypatch.setattr(db, "get_client", lambda: _Empty())
    profile, ok = db.fetch_profile("some-user")

    assert profile is None
    assert ok is True, "משתמש בלי פרופיל טופל כתקלה — הוא לא יוכל להיווצר"


# ─── ההשלכה המסוכנת ──────────────────────────────────────────────────────────

def test_a_failed_read_never_creates_a_family(monkeypatch):
    """זו השורה שהרסה את הנתונים: יצירת משפחה על סמך כישלון דורסת את
    השיוך הקיים ומנתקת את המשתמש מכל ההיסטוריה שלו."""
    created = []

    class _Recorder:
        def table(self, name):
            created.append(name)
            raise AssertionError(f"נוצרה כתיבה ל-{name} למרות שהשליפה נכשלה")

    monkeypatch.setattr(db, "get_client", lambda: _Recorder())
    monkeypatch.setattr(db, "fetch_profile", lambda uid: (None, False))

    assert db.ensure_family("some-user") is None
    assert created == []


def test_a_missing_profile_does_still_get_a_family(monkeypatch):
    """בקרת-נגד: הזהירות לא אמורה לשבור משתמש חדש אמיתי."""
    writes = []

    class _Fake:
        def table(self, name): writes.append(name); return self
        def insert(self, *a, **k): return self
        def update(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def execute(self): return self

    monkeypatch.setattr(db, "get_client", lambda: _Fake())
    monkeypatch.setattr(db, "fetch_profile", lambda uid: (None, True))

    assert db.ensure_family("some-user") is not None
    assert "families" in writes


# ─── מה שהמשתמש חווה ─────────────────────────────────────────────────────────

def test_login_is_refused_when_the_profile_cannot_be_read(client, monkeypatch):
    monkeypatch.setattr(app_module.db, "fetch_profile", lambda uid: (None, False))

    response = _login(client)

    assert response.status_code != 302, "נכנס למרות שהפרופיל לא נקרא"
    assert "נסה שוב" in response.get_data(as_text=True)
    with client.session_transaction() as sess:
        assert not sess.get("user_id"), "נפתח session בלי פרופיל"


def test_login_is_refused_when_the_family_cannot_be_created(client, monkeypatch):
    """session בלי משפחה הוא אפליקציה שאי אפשר לעשות בה כלום."""
    monkeypatch.setattr(app_module.db, "fetch_profile", lambda uid: (None, True))
    monkeypatch.setattr(app_module.db, "ensure_family", lambda uid: None)

    response = _login(client)

    assert response.status_code != 302
    with client.session_transaction() as sess:
        assert not sess.get("user_id")


def test_a_healthy_login_still_works(client, monkeypatch):
    """בקרת-נגד סופית: הזהירות לא חוסמת את המסלול התקין."""
    monkeypatch.setattr(app_module.db, "fetch_profile",
                        lambda uid: ({"name": "דנה", "avatar_initial": "ד",
                                      "family_id": "11111111-1111-1111-1111-111111111111"}, True))

    response = _login(client)

    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert sess["family_id"] == "11111111-1111-1111-1111-111111111111"
