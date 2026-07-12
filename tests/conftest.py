import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend import supabase_config as db

TEST_ACCOUNTS = {
    "a": {"email": "rls-test-family-a@smartfin.test", "password": "RlsTest123!"},
    "b": {"email": "rls-test-family-b@smartfin.test", "password": "RlsTest123!"},
}


def _login(key):
    account = TEST_ACCOUNTS[key]
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


@pytest.fixture(autouse=True)
def _start_authenticated_as_family_a(family_a):
    """כל בדיקה מתחילה עם ה-client מאומת כמשפחה א' כברירת מחדל — בדיקות
    שצריכות להחליף הקשר (למשל לבדוק גישה חוצת-משפחה) עושות זאת בעצמן."""
    db.set_auth_token(family_a["token"])
    yield
