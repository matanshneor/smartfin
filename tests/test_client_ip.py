"""
בדיקות לזיהוי כתובת הלקוח מאחורי ה-proxy של Railway.

התגלה באימות ה-rate limiting בפרודקשן: ProxyFix הוגדר עם x_proto ו-x_host
בלבד, בלי x_for, ולכן remote_addr היה צומת הקצה של Railway ולא המשתמש.
‏12 בקשות ממחשב אחד נספרו תחת ארבע כתובות והמגבלה לא נאכפה.

הצד המסוכן יותר הוא ההפוך: כל המשתמשים מגיעים דרך אותה קומץ כתובות קצה,
כך שמשתמש אחד רועש יכול היה למצות את המכסה ולנעול את ההתחברות לכולם.

הערך x_for=2 נמדד מול הפרודקשן ולא נוחש. Railway מוסיף שתי שכבות, ו-
‏X-Forwarded-For מגיע כ-"<לקוח>, <צומת קצה>". ProxyFix סופר מימין, ולכן
‏x_for=1 החזיר את צומת הקצה. הטסטים כאן מקבעים את הטופולוגיה הזאת — אם
Railway ישנה אותה, הם ייפלו וזו בדיוק המטרה.
"""
import pytest

from backend.app import app

pytestmark = pytest.mark.unit

EDGE       = "152.233.12.241"   # צומת קצה של Railway, כפי שנצפה בפועל
OTHER_EDGE = "152.233.13.166"

# ה-probe נרשם פעם אחת בלבד: Flask חוסם רישום מסלולים אחרי הבקשה הראשונה.
_captured = {}


@app.route("/__ip_probe")
def _ip_probe():
    from flask import request
    _captured["addr"] = request.remote_addr
    return "ok"


@pytest.fixture
def seen_ip():
    """מריצה בקשה עם שרשרת proxy נתונה ומחזירה מה Flask ראה כ-remote_addr —
    כלומר בדיוק המפתח שבו ישתמש get_remote_address."""
    app.config["TESTING"] = True

    def run(forwarded_for):
        _captured.clear()
        with app.test_client() as c:
            c.get("/__ip_probe",
                  headers={"X-Forwarded-For": forwarded_for},
                  environ_overrides={"REMOTE_ADDR": "100.64.0.2"})
        return _captured.get("addr")

    return run


def test_the_real_client_ip_is_used(seen_ip):
    assert seen_ip(f"203.0.113.7, {EDGE}") == "203.0.113.7"


def test_two_users_behind_one_edge_are_told_apart(seen_ip):
    """ליבת הבאג: שני משתמשים דרך אותו צומת חייבים לקבל מפתחות נפרדים,
    אחרת אחד ממצה את המכסה של השני."""
    first  = seen_ip(f"203.0.113.7, {EDGE}")
    second = seen_ip(f"198.51.100.23, {EDGE}")

    assert first != second
    assert {first, second} == {"203.0.113.7", "198.51.100.23"}


def test_one_user_across_two_edges_stays_one_key(seen_ip):
    """הצד השני: אותו משתמש דרך שני צמתי קצה נספר פעם אחת, אחרת המגבלה
    מוכפלת במספר הצמתים — וזה מה שקרה בפועל."""
    assert seen_ip(f"203.0.113.7, {EDGE}") == seen_ip(f"203.0.113.7, {OTHER_EDGE}")


def test_a_spoofed_entry_does_not_win(seen_ip):
    """ספירה מימין היא מה שמונע זיוף: ערך שהלקוח דוחף בעצמו נדחק שמאלה
    ולעולם לא נבחר. (בפועל Railway גם מוחק כותרות כאלה לפני שהן מגיעות —
    נמדד — אבל אנחנו לא נשענים על כך בלבד.)"""
    assert seen_ip(f"1.2.3.4, 203.0.113.7, {EDGE}") == "203.0.113.7"
