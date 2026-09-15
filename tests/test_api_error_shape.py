"""
בדיקות לצורת התשובה של מסלולי ה-API כשמשהו משתבש.

הבאג שזה מכסה: login_required החזיר redirect גם ל-38 מסלולי ה-API.
fetch עוקב אחרי הפניות בשקט, כך שהלקוח קיבל את דף ההתחברות כ-HTML עם
קוד 200, ניסה לפרסר אותו כ-JSON, ונפל ל-catch שאומר "שגיאת רשת".
המשתמש ניסה שוב וקיבל בדיוק אותו דבר, לנצח, בלי שום רמז שהפתרון הוא
להתחבר מחדש. אותו דבר קרה ב-404 וב-500.

הכלל שנבדק כאן: קריאה ל-/api/ מקבלת JSON עם קוד שגיאה אמיתי — לעולם
לא HTML, ולעולם לא 200 כשהיא נכשלה. ניווט רגיל ממשיך לקבל עמוד.
"""
import json

import pytest

from backend.app import app

pytestmark = pytest.mark.unit


@pytest.fixture
def anon():
    app.config["TESTING"] = True
    return app.test_client()


# ─── סשן שפג ─────────────────────────────────────────────────────────────────

# מדגם מייצג משלושת הסוגים: קריאה, כתיבה ומחיקה
_GUARDED = [
    ("GET",    "/api/categories"),
    ("GET",    "/api/family/members"),
    ("GET",    "/api/projects"),
    ("POST",   "/api/transactions"),
    ("DELETE", "/api/transactions/00000000-0000-0000-0000-000000000000"),
]


@pytest.mark.parametrize("method,path", _GUARDED)
def test_an_expired_session_returns_401_json_not_a_login_page(anon, method, path):
    response = anon.open(path, method=method)

    assert response.status_code == 401, (
        f"{method} {path} החזיר {response.status_code} — "
        "הלקוח יפרש הפניה לדף התחברות כ'שגיאת רשת' ויתקע"
    )
    assert response.mimetype == "application/json"
    assert json.loads(response.get_data(as_text=True))["error"]


def test_a_normal_page_still_redirects_to_the_login_form(anon):
    """בקרת-נגד: ההפרדה היא בין API לניווט, לא ביטול ההפניה."""
    response = anon.get("/settings")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# ─── שגיאות שרת ──────────────────────────────────────────────────────────────

def test_a_missing_api_route_returns_json(anon):
    response = anon.get("/api/no-such-thing")

    assert response.status_code == 404
    assert response.mimetype == "application/json"


def test_a_missing_page_still_returns_html(anon):
    response = anon.get("/no-such-page")

    assert response.status_code == 404
    assert response.mimetype == "text/html"


def _always_raises():
    raise RuntimeError("boom")


# נרשם ברמת המודול: Flask לא מרשה להוסיף מסלול אחרי הבקשה הראשונה
app.add_url_rule("/api/__boom", "test_api_boom", _always_raises)


def test_a_server_error_on_an_api_route_returns_json():
    """תקלת שרת אמיתית חייבת להגיע כשגיאה מזוהה. כשהיא מגיעה כ-HTML
    המשתמש רואה "שגיאת רשת" ומנסה שוב בקשה שלעולם לא תצליח."""
    app.config["TESTING"] = False          # אחרת Flask מרים את החריגה החוצה
    try:
        response = app.test_client().get("/api/__boom")
        assert response.status_code == 500
        assert response.mimetype == "application/json"
        assert json.loads(response.get_data(as_text=True))["error"]
    finally:
        app.config["TESTING"] = True


# ─── ההגנה בצד הלקוח ─────────────────────────────────────────────────────────

def test_every_page_behind_the_login_loads_the_401_guard():
    """שרת שמחזיר 401 לא עוזר אם אף אחד לא מקשיב לו. העמודים העצמאיים
    (onboarding) לא טוענים את core.js, ולכן ההגנה בקובץ נפרד."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent

    for template in ("base.html", "onboarding.html"):
        html = (root / "frontend/templates" / template).read_text(encoding="utf-8")
        assert "js/auth-guard.js" in html, f"{template} לא טוען את ההגנה"

    guard = (root / "frontend/static/js/auth-guard.js").read_text(encoding="utf-8")
    assert "401" in guard and "/login" in guard
