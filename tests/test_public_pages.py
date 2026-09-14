"""
בדיקות לעמודים הציבוריים: דף הנחיתה והעמודים המשפטיים.

עד היום "/" היה מוגן ב-login_required והפנה ישר ל-/login, כך שכל מי שקיבל
קישור נחת על טופס התחברות בלי לדעת מה האפליקציה עושה ולמה שימסור לה נתונים
פיננסיים. זה היה החוסם הראשון בהפצה.

הדבר שחייב כיסוי הוא בדיוק התכונה שנשברת בקלות ברפקטור: העמודים האלה
חייבים להיות נגישים **בלי** session. אם מישהו יחזיר את login_required
או ישנה את התנאי — הבדיקות כאן ייפלו.
"""
import pytest

from backend.app import app

pytestmark = pytest.mark.unit


@pytest.fixture
def anon():
    """לקוח בלי session — מבקר שרואה את האתר בפעם הראשונה."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def signed_in():
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]        = "00000000-0000-0000-0000-000000000000"
            sess["user_name"]      = "בדיקה"
            sess["avatar_initial"] = "ב"
            sess["family_id"]      = None
        yield c


@pytest.mark.parametrize("path", ["/", "/privacy", "/terms"])
def test_public_pages_need_no_session(anon, path):
    response = anon.get(path)

    assert response.status_code == 200, f"{path} לא נגיש למבקר אנונימי"


def test_the_landing_page_explains_and_invites(anon):
    """דף נחיתה שלא אומר מה האפליקציה עושה ולא מציע להירשם הוא סתם עמוד."""
    body = anon.get("/").get_data(as_text=True)

    assert "SmartFin" in body
    assert "/signup" in body, "חסרה קריאה לפעולה להרשמה"
    assert "/login" in body, "חסר קישור למי שכבר רשום"


def test_the_landing_page_links_to_the_legal_pages(anon):
    """הקישורים האלה הם הסיבה שהעמודים קיימים — בלעדיהם אף אחד לא יגיע אליהם."""
    body = anon.get("/").get_data(as_text=True)

    assert "/privacy" in body
    assert "/terms" in body


def test_the_landing_page_is_never_cached(anon):
    """אותה כתובת מגישה שני דברים שונים לפי מצב ההתחברות, אז שמירה במטמון
    של אחד מהם תציג אותו לקהל הלא נכון."""
    assert "no-store" in anon.get("/").headers.get("Cache-Control", "")


def test_a_signed_in_user_gets_the_app_not_the_landing_page(signed_in):
    """אותה כתובת, קהל אחר — מי שמחובר צריך לראות את האפליקציה."""
    body = signed_in.get("/").get_data(as_text=True)

    assert "פתיחת חשבון — בחינם" not in body, "משתמש מחובר קיבל את דף השיווק"


def test_signup_points_at_the_legal_pages(anon):
    """הסכמה לתנאים צריכה להופיע איפה שנרשמים, לא רק בפוטר."""
    body = anon.get("/signup").get_data(as_text=True)

    assert "/terms" in body
    assert "/privacy" in body
