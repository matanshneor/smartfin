import os
import sys

import pytest
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from backend import supabase_config as db

import _test_accounts


@pytest.fixture(scope="session")
def _test_pair():
    """שני חשבונות בדיקה זמניים לכל הריצה — נוצרים בפעם הראשונה שבדיקה
    צריכה אותם, ונמחקים בסוף עם כל מה שהשאירו (ראו ‎tests/_test_accounts.py‎).
    עד 4.10 אלה היו שני משתמשים קבועים במסד הייצור."""
    if not os.environ.get("SUPABASE_URL"):
        pytest.skip("אין SUPABASE_URL — הבדיקות מול המסד האמיתי רצות רק מקומית")
    pair = _test_accounts.create_pair("pytest")
    yield pair
    _test_accounts.purge([a["user_id"] for a in pair.values()])


def _signed_in(account):
    db.set_auth_token(account["token"])
    return {k: account[k] for k in ("user_id", "family_id", "token")}


@pytest.fixture(scope="session")
def family_a(_test_pair):
    return _signed_in(_test_pair["a"])


@pytest.fixture(scope="session")
def family_b(_test_pair):
    return _signed_in(_test_pair["b"])


def category_of(family_id: str, type_: str = "expense") -> str:
    """קטגוריה קיימת של המשפחה מהסוג הזה — ואם אין, יוצרת אחת קבועה.

    עסקת בית בלי קטגוריה נדחית במסד (‎transactions_category_required‎),
    אז כל בדיקה שמכניסה עסקה ישירות צריכה אחת. הטוקן הפעיל חייב להיות
    של בן המשפחה הזו."""
    table = db.get_client().table("categories")
    found = table.select("id").eq("family_id", family_id).eq("type", type_) \
        .limit(1).execute().data
    if found:
        return found[0]["id"]
    return table.insert({"family_id": family_id, "name": f"TEST-{type_}", "icon": "🧪",
                         "type": type_, "is_custom": True}).execute().data[0]["id"]


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
    # המייל העדכני מ-Supabase (‎_current_email‎ ב-app). ברירת מחדל בבדיקות:
    # "אי אפשר לדעת" — והאפליקציה נופלת למייל שבסשן, כמו לפני 1.10.
    # בדיקה שצריכה מייל אחר מחליפה את זה בעצמה.
    monkeypatch.setattr(db, "get_auth_email", lambda token: (None, None))
    # הממוצע החודשי לכל קטגוריה בהגדרות (רעיון 38) — ברירת מחדל: אין
    _real_averages = db.category_monthly_averages
    monkeypatch.setattr(db, "category_monthly_averages", lambda *a, **k: {})
    monkeypatch.setattr(db, "_real_category_monthly_averages", _real_averages, raising=False)
    # "₪5,000 ← ₪5,500 מאוקטובר" בהגדרות (רעיון 40) — ברירת מחדל: אין שינויים
    monkeypatch.setattr(db, "recurring_price_changes", lambda *a, **k: {})
    # וגם רשת ישירה. ‎send_reset_email‎, ‎upload_receipt‎ ו-‎delete_receipts‎
    # פונים ל-Supabase ב-httpx ולא דרך ‎get_client‎ — ובדיקת ביקורת על "שכחתי
    # סיסמה" שלחה ככה בקשת איפוס אמיתית (30.9.2026, לכתובת שלא רשומה, אז
    # לא נשלח מייל). ב-CI אין ‎SUPABASE_URL‎ והבדיקה נכשלה; אצלנו היא עברה.
    import httpx
    for verb in ("request", "get", "post", "put", "patch", "delete"):
        monkeypatch.setattr(httpx, verb, lambda *a, **k: _refuse())
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
