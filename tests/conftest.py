import os
import sys

import pytest
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend import supabase_config as db

# הסיסמאות מגיעות מהסביבה ולא מהקוד. הריפו ציבורי, וסיסמה שכתובה בו היא
# סיסמה עובדת לחשבון אמיתי במסד האמיתי — כל מי שקורא את הקוד יכול להתחבר
# איתה לאפליקציה. הערכים יושבים ב-.env המקומי, שאינו במעקב גיט.
TEST_ACCOUNTS = {
    "a": {"email": os.environ.get("RLS_TEST_EMAIL_A", "rls-test-family-a@smartfin.test"),
          "password": os.environ.get("RLS_TEST_PASSWORD_A")},
    "b": {"email": os.environ.get("RLS_TEST_EMAIL_B", "rls-test-family-b@smartfin.test"),
          "password": os.environ.get("RLS_TEST_PASSWORD_B")},
}


def _login(key):
    account = TEST_ACCOUNTS[key]
    if not account["password"]:
        pytest.skip(
            f"חסרה RLS_TEST_PASSWORD_{key.upper()} בסביבה. הבדיקות מול המסד "
            f"האמיתי דורשות את סיסמאות חשבונות הבדיקה; הן לא בקוד בכוונה "
            f"(ראו tests/setup_rls_test_users.py)."
        )
    response, err = db.sign_in(account["email"], account["password"])
    if err:
        pytest.exit(
            f"בדיקות ה-RLS דורשות משתמשי בדיקה קבועים שכבר קיימים בפרויקט "
            f"Supabase. הרץ פעם אחת: python3 tests/setup_rls_test_users.py "
            f"(שגיאת התחברות ל-{account['email']}: {err})"
        )
    db.set_auth_token(response.session.access_token)
    profile = db.get_profile(response.user.id)
    return {
        "user_id": response.user.id,
        "family_id": profile["family_id"],
        "token": response.session.access_token,
    }


@pytest.fixture(scope="session")
def family_a():
    return _login("a")


@pytest.fixture(scope="session")
def family_b():
    return _login("b")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "unit: בדיקה טהורה שלא נוגעת ב-Supabase — לא מתחברת ולא דורשת משתמשי בדיקה",
    )


@pytest.fixture(autouse=True)
def _unit_tests_cannot_reach_supabase(request, monkeypatch):
    """אוכף את מה שהסימון ‎unit‎ הבטיח — ולא אכף.

    הסימון תיעד "לא נוגעת ב-Supabase", אבל שום דבר לא מנע את זה. בדיקה
    שהסתמכה על ולידציה בשרת כדי לא להגיע ל-‎db.sign_up‎ פשוט הגיעה אליו
    ברגע שהוולידציה הוסרה — למשל בבדיקת מוטציה — **ויצרה חשבון אמיתי
    במסד הייצור**. זה קרה, ב-20 בספטמבר 2026, עם ‎israel@gmail‎.

    הכשל היה גם שקט לחלוטין: הבדיקה עברה. אז מכאן ‎get_client‎ מסרבת
    לעבוד בבדיקות יחידה, וכל נגיעה ברשת נכשלת בקול עם ההסבר."""
    if "unit" not in request.keywords:
        yield
        return

    def _refuse():
        raise AssertionError(
            "בדיקת יחידה ניסתה לפנות ל-Supabase האמיתי. או שחסר "
            "monkeypatch על הפונקציה שנקראה, או שהבדיקה הזאת אינה unit."
        )

    monkeypatch.setattr(db, "get_client", _refuse)
    yield


@pytest.fixture(autouse=True)
def _start_authenticated_as_family_a(request):
    """כל בדיקה מתחילה עם ה-client מאומת כמשפחה א' כברירת מחדל — בדיקות
    שצריכות להחליף הקשר (למשל לבדוק גישה חוצת-משפחה) עושות זאת בעצמן.

    בדיקות המסומנות ב-@pytest.mark.unit מדלגות על ההתחברות: הן בודקות לוגיקה
    טהורה, ולוגין מיותר גם מאט אותן וגם שורף מהמכסה של 10 התחברויות לדקה."""
    if "unit" in request.keywords:
        yield
        return
    family_a = request.getfixturevalue("family_a")
    db.set_auth_token(family_a["token"])
    yield
