"""
בדיקות למסנן שמנקה אירועי Sentry לפני שליחה.

SmartFin מטפלת בנתונים פיננסיים, ומסלול סריקת הקבלה נושא תמונה של קבלה
אמיתית. שליחת גוף הבקשה לשירות חיצוני סותרת ישירות את מדיניות הפרטיות,
ולכן ההבטחה הזאת צריכה להיאכף בבדיקה ולא רק להיכתב בהערה: שדרוג עתידי של
ברירות המחדל ב-SDK לא יורגש בשום דרך אחרת.

הבדיקות כאן כיסו בתחילה רק את event["request"] — בדיוק החלק שכן נוקה.
הן עברו במלואן בזמן שהמשתנים המקומיים של כל frame, ובהם הסיסמה עצמה,
נשלחו החוצה. בדיקה שמאשרת רק את מה שכבר עובד גרועה מאין בדיקה, כי היא
קונה ביטחון בלי לספק אותו — ולכן החלק החדש למטה בודק את מה שדלף.

טהורות לגמרי — המסנן הוא פונקציה על מילון.
"""
import pytest

from backend.app import _scrub_event

pytestmark = pytest.mark.unit


def test_request_body_is_removed():
    """הגוף של /api/receipts/scan מכיל תמונת קבלה."""
    event = {"request": {"data": {"image": "base64-of-a-real-receipt"}, "url": "/api/receipts/scan"}}

    assert "data" not in _scrub_event(event, {})["request"]


def test_cookies_are_removed():
    """העוגייה נושאת את טוקני Supabase — שליחתה שקולה למסירת החשבון."""
    event = {"request": {"cookies": {"session": "eyJhbGciOi..."}}}

    assert "cookies" not in _scrub_event(event, {})["request"]


@pytest.mark.parametrize("header", ["Cookie", "Authorization"])
def test_sensitive_headers_are_removed(header):
    event = {"request": {"headers": {header: "secret", "User-Agent": "Safari"}}}

    headers = _scrub_event(event, {})["request"]["headers"]
    assert header not in headers
    assert headers["User-Agent"] == "Safari", "כותרות לא רגישות נשארות — הן עוזרות לאבחן"


def test_the_useful_parts_survive():
    """הניקוי חייב להשאיר מספיק כדי שהדיווח יהיה שווה משהו."""
    event = {
        "request":   {"url": "/month", "method": "GET", "data": {"x": 1}},
        "exception": {"values": [{"type": "KeyError"}]},
    }

    scrubbed = _scrub_event(event, {})
    assert scrubbed["request"]["url"] == "/month"
    assert scrubbed["request"]["method"] == "GET"
    assert scrubbed["exception"]["values"][0]["type"] == "KeyError"


def test_an_event_without_a_request_section_is_untouched():
    """שגיאות ברקע (למשל סקריפט) מגיעות בלי request — אסור שזה יתפוצץ."""
    event = {"exception": {"values": [{"type": "ValueError"}]}}

    assert _scrub_event(event, {}) == event


# ─── מה שלא היה מכוסה, ודלף ──────────────────────────────────────────────────

def test_local_variables_never_leave_the_server():
    """הדליפה האמיתית. ה-SDK מצרף לכל frame את המשתנים שהיו בזיכרון, אז
    חריגה במסלול התחברות שלחה את הסיסמה עצמה לשירות חיצוני."""
    event = {"exception": {"values": [{
        "type": "RuntimeError",
        "stacktrace": {"frames": [
            {"function": "login", "vars": {"password": "hunter2",
                                           "identifier": "dana@example.com"}},
            {"function": "inject_auth", "vars": {"refresh_token": "v1.Mr0..."}},
        ]},
    }]}}

    frames = _scrub_event(event, {})["exception"]["values"][0]["stacktrace"]["frames"]

    for frame in frames:
        assert "vars" not in frame, f"משתנים מקומיים נשלחו מ-{frame['function']}"


def test_the_stack_itself_survives():
    """בקרת-נגד: בלי שמות הפונקציות הדיווח חסר ערך."""
    event = {"exception": {"values": [{"stacktrace": {"frames": [
        {"function": "scan_receipt_route", "lineno": 1420, "vars": {"image_bytes": b"..."}},
    ]}}]}}

    frame = _scrub_event(event, {})["exception"]["values"][0]["stacktrace"]["frames"][0]
    assert frame["function"] == "scan_receipt_route"
    assert frame["lineno"] == 1420


def test_the_invite_code_in_the_query_string_is_removed():
    """‎/api/family/preview?code=XXXXXX — קוד הזמנה הוא גישה מלאה למשפחה."""
    event = {"request": {"url": "/api/family/preview", "query_string": "code=AB12CD"}}

    assert "query_string" not in _scrub_event(event, {})["request"]


@pytest.mark.parametrize("key", ["password", "access_token", "api_key", "image_bytes"])
def test_secrets_sent_explicitly_in_extra_are_masked(key):
    """מה שהקוד ישלח בעצמו מחר, לא רק מה שה-SDK אוסף היום."""
    event = {"extra": {key: "sensitive", "family_id": "11111111"}}

    scrubbed = _scrub_event(event, {})["extra"]
    assert scrubbed[key] == "[scrubbed]"
    assert scrubbed["family_id"] == "11111111", "מזהים שימושיים לאבחון נשארים"


def test_breadcrumb_data_is_masked():
    """ה-SDK מתעד ב-breadcrumbs בקשות שקדמו לשגיאה."""
    event = {"breadcrumbs": [
        {"category": "http", "data": {"authorization": "Bearer ey...", "url": "/api/x"}},
    ]}

    data = _scrub_event(event, {})["breadcrumbs"][0]["data"]
    assert data["authorization"] == "[scrubbed]"
    assert data["url"] == "/api/x"


def test_the_sdk_is_configured_not_to_collect_locals_in_the_first_place():
    """הניקוי הוא השכבה השנייה. הראשונה היא לא לאסוף אותם מלכתחילה —
    ובלעדיה כל נתיב שהמסנן לא חשב עליו נשאר פתוח."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "backend/app.py").read_text(encoding="utf-8")

    assert "include_local_variables=False" in src


def test_a_malformed_event_does_not_crash_the_filter():
    """המסנן רץ על כל שגיאה. אם הוא עצמו מתפוצץ, איבדנו את הדיווח."""
    for event in ({}, {"exception": None}, {"breadcrumbs": [None]},
                  {"extra": "not-a-dict"}, {"exception": {"values": [{}]}}):
        _scrub_event(event, {})
