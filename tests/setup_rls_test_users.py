"""
הרצה חד-פעמית: יוצר שני משתמשי בדיקה קבועים (עם משפחות נפרדות) לסוויית
בדיקות ה-RLS ב-tests/test_rls_isolation.py. לא צריך להריץ שוב אם המשתמשים
כבר קיימים — signup חוזר על אימייל קיים פשוט נכשל בשקט ונדלג עליו.

הרצה: python3 tests/setup_rls_test_users.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend import supabase_config as db

TEST_ACCOUNTS = [
    {"email": "rls-test-family-a@smartfin.test", "password": "RlsTest123!", "name": "בדיקת RLS א"},
    {"email": "rls-test-family-b@smartfin.test", "password": "RlsTest123!", "name": "בדיקת RLS ב"},
]


def main():
    for account in TEST_ACCOUNTS:
        response, err = db.sign_up(account["email"], account["password"], account["name"])
        if err:
            print(f"[skip] {account['email']}: {err} (כנראה כבר קיים — זה בסדר)")
        else:
            print(f"[created] {account['email']}")

        # מתחברים כדי לוודא שיש למשתמש משפחה (ensure_family, כמו בכל התחברות ראשונה רגילה)
        login_response, login_err = db.sign_in(account["email"], account["password"])
        if login_err:
            print(f"[ERROR] לא הצלחתי להתחבר בתור {account['email']}: {login_err}")
            continue
        db.set_auth_token(login_response.session.access_token)
        profile = db.get_profile(login_response.user.id)
        family_id = profile.get("family_id") if profile else None
        if not family_id:
            family_id = db.ensure_family(login_response.user.id, f"משפחת בדיקה ({account['name']})")
        print(f"    user_id={login_response.user.id} family_id={family_id}")


if __name__ == "__main__":
    main()
