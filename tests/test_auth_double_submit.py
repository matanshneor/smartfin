"""
בדיקות ללחיצה כפולה בטפסי ההתחברות וההרשמה.

זה לא באג תיאורטי: טבלת login_events מראה שכמעט כל התחברות רשומה
פעמיים בהפרש שנייה אחת. הסיבה היא ששני הטפסים האלה היו היחידים
באפליקציה בלי נעילת כפתור, ובאפליקציה המותקנת בטלפון אין אפילו ספינר
של דפדפן — אז אחרי הקשה המסך לא מגיב, והמשתמש לוחץ שוב.

הלחיצה השנייה שורפת מהמכסה של 10 לדקה, וחציית המכסה הנחיתה את המשתמש
על error.html שיש בו רק "חזור לדף הראשי": בלי כפתור חזרה, בלי הטופס,
ובלי מה שהקליד.
"""
from pathlib import Path

import pytest

from backend.app import app, limiter

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def anon():
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture(autouse=True)
def _clean_rate_limit_counters():
    """המונים של flask_limiter חיים בזיכרון התהליך ולא פגים בתוך ריצת
    הבדיקות. בלי הניקוי הזה הבדיקות כאן, שממצות את המכסה בכוונה, מפילות
    כל בדיקה אחרת שמתחברת אחריהן — וזה נראה כמו באג במקום אחר לגמרי."""
    limiter.reset()
    yield
    limiter.reset()


# ─── הנעילה בדפדפן ───────────────────────────────────────────────────────────

def test_both_auth_forms_lock_their_submit_button():
    js = (_ROOT / "frontend/static/js/login.js").read_text(encoding="utf-8")

    for panel in ("loginPanel", "signupPanel"):
        assert panel in js, f"{panel} לא מקבל נעילת שליחה"
    assert "disabled = true" in js


def test_the_lock_can_always_be_released():
    """נעילה בלי שחרור גרועה מהבאג: טופס מת שאי אפשר לצאת ממנו.
    שני מסלולי השחרור — שסתום זמן, וחזרה מזיכרון הדפדפן."""
    js = (_ROOT / "frontend/static/js/login.js").read_text(encoding="utf-8")

    assert "setTimeout(release" in js, "אין שסתום ביטחון לשחרור הכפתור"
    assert "pageshow" in js, "חזרה עם 'אחורה' תשאיר את הכפתור נעול"


# ─── חסימת הקצב לא מובילה יותר למבוי סתום ────────────────────────────────────

def _exhaust_login_limit(client):
    """המגבלה היא 10 לדקה; הבקשה ה-11 נחסמת."""
    last = None
    for _ in range(12):
        last = client.post("/login", data={"identifier": "x@y.z", "password": "nope"})
        if last.status_code == 429:
            return last
    return last


def test_hitting_the_rate_limit_returns_the_login_form_not_a_dead_end(anon):
    response = _exhaust_login_limit(anon)

    assert response.status_code == 429, "המגבלה לא נאכפה — הבדיקה לא בדקה כלום"
    body = response.get_data(as_text=True)
    assert 'id="loginPanel"' in body, "המשתמש נזרק מהטופס במקום לחזור אליו"
    assert "יותר מדי ניסיונות" in body
    assert "חזור לדף הראשי" not in body, "עדיין מוגש דף השגיאה חסר המוצא"


def test_the_rate_limited_form_still_remembers_who_you_are(anon):
    """מי שנחסם אחרי לחיצה כפולה לא צריך להקליד את המייל שלו מחדש."""
    anon.set_cookie("sf_last_id", "dana@example.com")

    response = _exhaust_login_limit(anon)

    assert 'value="dana@example.com"' in response.get_data(as_text=True)
