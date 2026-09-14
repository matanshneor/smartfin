"""
בדיקות לזיהוי כתובת הלקוח מאחורי ה-proxy של Railway.

התגלה באימות ה-rate limiting בפרודקשן: ProxyFix הוגדר עם x_proto ו-x_host
בלבד, בלי x_for. בלי זה Flask מתעלם מ-X-Forwarded-For ו-remote_addr הוא
צומת הקצה של Railway — כך ש-12 בקשות ממחשב אחד נספרו תחת ארבע כתובות
שונות והמגבלה פשוט לא נאכפה.

הצד המסוכן יותר הוא ההפוך: כל המשתמשים חולקים את אותן כתובות proxy, ולכן
משתמש אחד רועש יכול היה למצות את המכסה ולנעול את ההתחברות לכל השאר.

הבדיקות האלה מתעדות את ההתנהגות בשכבת ה-WSGI ולא דורשות רשת.
"""
import pytest

from backend.app import app

pytestmark = pytest.mark.unit


# ה-probe נרשם פעם אחת בלבד: Flask חוסם רישום מסלולים אחרי הבקשה הראשונה.
_captured = {}


@app.route("/__ip_probe")
def _ip_probe():
    from flask import request
    _captured["addr"] = request.remote_addr
    return "ok"


@pytest.fixture
def seen_ip():
    """מחזירה פונקציה שמריצה בקשה עם כותרות נתונות ומדווחת מה Flask ראה
    כ-remote_addr — כלומר בדיוק מה ש-get_remote_address ישתמש בו כמפתח."""
    app.config["TESTING"] = True

    def run(headers=None, environ=None):
        _captured.clear()
        with app.test_client() as c:
            c.get("/__ip_probe", headers=headers or {},
                  environ_overrides=environ or {})
        return _captured.get("addr")

    return run


def test_the_forwarded_client_ip_is_used(seen_ip):
    """הכתובת של המשתמש, לא של ה-proxy."""
    addr = seen_ip(
        headers={"X-Forwarded-For": "203.0.113.7"},
        environ={"REMOTE_ADDR": "10.0.0.1"},   # צומת הקצה
    )

    assert addr == "203.0.113.7"


def test_two_users_behind_one_proxy_are_told_apart(seen_ip):
    """הליבה של הבאג: שני משתמשים שמגיעים דרך אותו proxy חייבים לקבל
    מפתחות נפרדים, אחרת אחד מהם ממצה את המכסה של השני."""
    first  = seen_ip(headers={"X-Forwarded-For": "203.0.113.7"},
                     environ={"REMOTE_ADDR": "10.0.0.1"})
    second = seen_ip(headers={"X-Forwarded-For": "198.51.100.23"},
                     environ={"REMOTE_ADDR": "10.0.0.1"})

    assert first != second


def test_one_user_through_two_proxy_nodes_stays_one_key(seen_ip):
    """הצד השני של הבאג: אותו משתמש דרך שני צמתי קצה שונים נספר פעם אחת,
    אחרת המגבלה מוכפלת במספר הצמתים."""
    via_first  = seen_ip(headers={"X-Forwarded-For": "203.0.113.7"},
                         environ={"REMOTE_ADDR": "152.233.12.241"})
    via_second = seen_ip(headers={"X-Forwarded-For": "203.0.113.7"},
                         environ={"REMOTE_ADDR": "152.233.13.166"})

    assert via_first == via_second == "203.0.113.7"


def test_only_the_nearest_hop_is_trusted(seen_ip):
    """x_for=1 בכוונה: לקוח יכול לזייף X-Forwarded-For, ורק הערך שה-proxy
    שלנו הוסיף — האחרון — אמין. ערכים מוקדמים יותר ברשימה לא נספרים."""
    addr = seen_ip(
        headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.7"},
        environ={"REMOTE_ADDR": "10.0.0.1"},
    )

    assert addr == "203.0.113.7", "כתובת מזויפת בתחילת השרשרת לא אמורה לגבור"
