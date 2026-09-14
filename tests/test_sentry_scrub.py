"""
בדיקות למסנן שמנקה אירועי Sentry לפני שליחה.

SmartFin מטפלת בנתונים פיננסיים, ומסלול סריקת הקבלה נושא תמונה של קבלה
אמיתית. שליחת גוף הבקשה לשירות חיצוני סותרת ישירות את מדיניות הפרטיות,
ולכן ההבטחה הזאת צריכה להיאכף בבדיקה ולא רק להיכתב בהערה: שדרוג עתידי של
ברירות המחדל ב-SDK לא יורגש בשום דרך אחרת.

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
