"""
בדיקות לשלוש הקשחות שהביקורת מצאה.

16 — מסלולים רגישים בלי הגבלת קצב. שלושה מהם מאמתים סיסמה מול Supabase,
     כלומר אורקל לניחוש סיסמאות למי שהשיג סשן; ההגבלה על /login לא עוזרת
     שם, כי אלו מסלולים אחרים. הרביעי, השלמת איפוס סיסמה, אינו מאומת כלל.

17 — שדות בעסקה התקבלו מהלקוח בלי אימות. RLS בודקת רק את family_id בשורה
     שנכתבת ולא את user_id, אז אפשר היה לתלות הוצאה על בן הזוג. ופרויקט
     אישי היה מוגן בקריאה בלבד — הכתיבה סיננה לפי משפחה בלבד, כך שבן
     משפחה יכול היה למחוק פרויקט שאסור לו אפילו לראות.

18 — ‎/logout‎ היה GET, כלומר ניתן להפעלה מאתר אחר; סכומים בלי גבול עליון
     נפלו על מגבלת העמודה עם הודעה גנרית שמובילה למבוי סתום.
"""
import inspect
from pathlib import Path

import pytest

from backend import app as app_module
from backend.app import app, _parse_amount, limiter

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent


# ─── 16: הגבלת קצב ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("endpoint,why", [
    ("update_password",       "אורקל לניחוש הסיסמה הנוכחית"),
    ("reset_account_route",   "אורקל סיסמה + מחיקת כל עסקאות המשפחה"),
    ("delete_account_route",  "אורקל סיסמה + מחיקת חשבון לצמיתות"),
    ("reset_password_submit", "לא מאומת, ומקבל טוקן שחזור מגוף הבקשה"),
])
def test_the_sensitive_routes_are_rate_limited(endpoint, why):
    src = inspect.getsource(getattr(app_module, endpoint))

    assert "@limiter.limit" in src, f"{endpoint} ללא הגבלה — {why}"


def test_the_destructive_ones_are_limited_harder_than_the_rest():
    """אין תרחיש לגיטימי של מחיקת חשבון או איפוס נתונים שוב ושוב."""
    for endpoint in ("reset_account_route", "delete_account_route"):
        assert "per hour" in inspect.getsource(getattr(app_module, endpoint))


# ─── 17: אימות שדות ─────────────────────────────────────────────────────────

def _user():
    return {"id": "11111111-1111-1111-1111-111111111111",
            "family_id": "22222222-2222-2222-2222-222222222222"}


@pytest.fixture
def attribution_on(monkeypatch):
    monkeypatch.setattr(app_module, "family_settings",
                        lambda: {"owner_attribution": {"expense": True}})


def test_an_owner_outside_the_family_is_refused(attribution_on, monkeypatch):
    """לא דליפת מידע אלא זיוף שיוך — והפילוח 'לפי בן משפחה' מתבסס עליו."""
    monkeypatch.setattr(app_module.db, "get_family_members",
                        lambda fid: [{"id": _user()["id"]}])

    owner, err = app_module._resolve_owner(
        {"owner": "99999999-9999-9999-9999-999999999999"}, _user(), "expense")

    assert owner is None
    assert "אינו במשפחה" in err


def test_a_real_family_member_is_still_accepted(attribution_on, monkeypatch):
    """בקרת-נגד: שיוך לגיטימי חייב להמשיך לעבוד."""
    mate = "33333333-3333-3333-3333-333333333333"
    monkeypatch.setattr(app_module.db, "get_family_members",
                        lambda fid: [{"id": _user()["id"]}, {"id": mate}])

    owner, err = app_module._resolve_owner({"owner": mate}, _user(), "expense")

    assert (owner, err) == (mate, None)


def test_a_category_of_the_wrong_type_is_refused(monkeypatch):
    monkeypatch.setattr(app_module.db, "get_categories",
                        lambda fid: [{"id": "cat-1", "type": "income"}])

    _, err = app_module._validated_category("cat-1", _user(), "expense")

    assert "אינה מתאימה" in err


def test_no_category_at_all_is_allowed(monkeypatch):
    """בקרת-נגד: עסקה ללא קטגוריה היא מצב תקין."""
    assert app_module._validated_category(None, _user(), "expense") == (None, None)


def test_every_project_route_goes_through_the_access_gate():
    """שמונה מסלולים סיננו לפי משפחה בלבד. הכלל נאכף בשער אחד ולא
    בשמונה עותקים, כי השמיני הוא זה שנשכח."""
    src = (_ROOT / "backend/app.py").read_text(encoding="utf-8")

    for fn in ("update_project_route", "delete_project_route",
               "share_project_route", "unshare_project_route",
               "list_project_categories_route", "add_project_category_route",
               "update_project_category_route", "delete_project_category_route"):
        block = src[src.index(f"def {fn}(") - 120:src.index(f"def {fn}(")]
        assert "@project_access_required" in block, f"{fn} ללא שער גישה"


def test_a_personal_project_answers_not_found_rather_than_forbidden():
    """פרויקט אישי הוא פרטי — התשובה אסור שתאשר שהוא קיים."""
    src = inspect.getsource(app_module.project_access_required)

    assert "404" in src
    assert "403" not in src


# ─── 18: גבולות וסכומים ─────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,reason", [
    (999_999_999, "גדול מדי"),
    (0.004,       "קטן מדי"),
    (0,           "חיובי"),
    (-5,          "חיובי"),
    ("abc",       "מספר"),
    (float("inf"), "חיובי"),
])
def test_bad_amounts_are_explained_not_swallowed(raw, reason):
    """בלי הבדיקות האלה Postgres נכשל והמשתמש מקבל 'נסה שוב' — אז הוא
    מנסה שוב את אותו קלט, ונכשל שוב, בלי שום רמז למה."""
    value, err = _parse_amount(raw)

    assert value is None
    assert reason in err


@pytest.mark.parametrize("raw", [1, 0.01, 12.5, "1250.75", 99_999_999])
def test_normal_amounts_still_pass(raw):
    value, err = _parse_amount(raw)
    assert err is None and value > 0


def test_logging_out_is_not_something_another_site_can_trigger():
    """GET /logout אפשר להפעיל עם <img src="...">. SameSite=Lax מתיר
    בדיוק את הצורה הזאת של ניווט."""
    html = (_ROOT / "frontend/templates/settings.html").read_text(encoding="utf-8")

    assert 'method="POST" action="{{ url_for(\'logout\') }}"' in html, \
        "כפתור היציאה עדיין קישור GET"
