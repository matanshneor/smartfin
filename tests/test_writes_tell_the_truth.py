"""כתיבה שלא נגעה בשום שורה אמרה "נשמר".

הסבב הקודם תיקן את זה לעסקאות. שמונה מסלולי כתיבה נוספים נשארו: עריכת
קטגוריה, סידור קטגוריות, עריכת פרויקט, קטגוריות פרויקט, מחיקת פרויקט
ושם המשפחה. כולם עשו ‎.update(...).eq(...).execute()‎ ואז ‎return True‎
בלי להסתכל ב-‎.data‎.

התרחיש הוא לא תיאורטי. אמא משנה את השם של "מסעדות" בזמן שאבא מוחק את
אותה קטגוריה שנייה קודם: ה-‎PUT‎ לא מתאים לשום שורה, הפונקציה מחזירה
‎True‎, המסלול מחזיר ‎{"status":"ok"}‎ וה-JS צובע את השם החדש על המסך.
אמא בטוחה שהשינוי נשמר. הוא לא.

זה אותו דפוס בדיוק של ‎DataUnavailable‎ — הצלחה מדומה — רק בכיוון
הכתיבה, ובו הוא שקט אפילו יותר: אין אפילו מספר שנראה שגוי.
"""
import pytest

from backend import supabase_config as db
from tests._fake_db import FakeSupabase

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"
_OTHER = "99999999-9999-9999-9999-999999999999"


@pytest.fixture
def fake(monkeypatch):
    f = FakeSupabase(
        categories=[{"id": "c1", "family_id": _FAM, "name": "מסעדות",
                     "type": "expense", "icon": "🍽", "is_custom": True, "sort_order": 1}],
        projects=[{"id": "p1", "family_id": _FAM, "name": "שיפוץ", "archived": False,
                   "track_expense": True, "track_income": False, "track_savings": False,
                   "budget_target": 5000, "description": None, "icon": "🔨"}],
        project_categories=[{"id": "pc1", "project_id": "p1", "family_id": _FAM,
                             "name": "חומרים", "icon": "🧱"}],
        families=[{"id": _FAM, "name": "שניאור", "settings": {}}],
        transactions=[{"id": "t1", "family_id": _FAM, "project_id": "p1",
                       "amount": 800.0, "type": "expense", "date": "2026-09-01"},
                      {"id": "t2", "family_id": _FAM, "project_id": "p1",
                       "amount": 200.0, "type": "expense", "date": "2026-09-02"}],
    )
    monkeypatch.setattr(db, "get_client", lambda: f)
    monkeypatch.setattr(db, "_invalidate_family_cache", lambda *a, **k: None)
    return f


# ═══ הדבר עצמו קיים ═══════════════════════════════════════════════════════════

def test_editing_a_category_that_exists_reports_success(fake):
    assert db.update_category("c1", _FAM, "אוכל בחוץ", "🍕") is True
    assert fake.rows("categories")[0]["name"] == "אוכל בחוץ"


def test_renaming_the_family_reports_success(fake):
    assert db.update_family_name(_FAM, "משפחת כהן") is True
    assert fake.rows("families")[0]["name"] == "משפחת כהן"


def test_editing_a_project_category_reports_success(fake):
    assert db.update_project_category("pc1", "p1", _FAM, "צבע", "🎨") is True


# ═══ ומה שקורה כשהוא כבר לא ═══════════════════════════════════════════════════

def test_editing_a_category_someone_else_deleted_is_not_success(fake):
    """הלב, והתרחיש האמיתי: בן משפחה אחר מחק אותה שנייה קודם."""
    fake.tables["categories"] = []

    assert db.update_category("c1", _FAM, "אוכל בחוץ", "🍕") is False


def test_a_category_of_another_family_cannot_be_renamed(fake):
    """הבידוד. ‎eq("family_id")‎ מסנן, אבל התשובה אמרה "נשמר" בכל מקרה,
    אז נראה היה שזה עבד."""
    fake.tables["categories"][0]["family_id"] = _OTHER

    assert db.update_category("c1", _FAM, "שלי עכשיו", "🍕") is False
    assert fake.rows("categories")[0]["name"] == "מסעדות"


def test_renaming_a_family_that_is_not_there_is_not_success(fake):
    assert db.update_family_name("fam-נעלם", "משפחת כהן") is False


def test_editing_a_project_category_of_another_project_is_not_success(fake):
    assert db.update_project_category("pc1", "p-אחר", _FAM, "צבע", "🎨") is False


def test_deleting_a_project_category_that_is_gone_is_not_success(fake):
    fake.tables["project_categories"] = []

    assert db.delete_project_category("pc1", "p1", _FAM) is False


def test_editing_a_project_that_is_gone_is_not_success(fake):
    fake.tables["projects"] = []

    assert db.update_project("p1", _FAM, "שיפוץ", 5000, None, "🔨",
                             True, False, False) is False


# ═══ מחיקת פרויקט מדווחת כמה כסף נעלם ═════════════════════════════════════════

def test_deleting_a_project_with_its_transactions_says_how_many(fake):
    """"מחק גם עסקאות" לא נשא שום מספר. זו הפעולה ההרסנית ביותר שכל חבר
    יכול לעשות בלי סיסמה ובלי הרשאת מנהל."""
    ok, wiped = db.delete_project("p1", _FAM, delete_transactions=True)

    assert ok is True
    assert wiped == 2
    assert fake.rows("transactions") == []


def test_deleting_a_project_without_its_transactions_leaves_the_money(fake):
    """ברירת המחדל: העסקאות חוזרות להיספר תחת הקטגוריה הרגילה שלהן."""
    ok, wiped = db.delete_project("p1", _FAM, delete_transactions=False)

    assert ok is True and wiped == 0
    assert len(fake.rows("transactions")) == 2


def test_deleting_a_project_that_is_gone_is_not_success(fake):
    fake.tables["projects"] = []

    ok, wiped = db.delete_project("p1", _FAM, delete_transactions=False)

    assert ok is False and wiped == 0
