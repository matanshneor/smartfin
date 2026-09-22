"""מה ששובר כשמגיעים זרים, ומה שנשבר בלי שאף אחד יידע.

כל אחד מהפריטים כאן היה **נכון** באפליקציה של משפחה אחת ומפסיק להיות
נכון ברגע שההרשמה פתוחה:

- 23 מסלולי כתיבה בלי שום הגבלת קצב, ומאחוריהם טריגר שמעתיק כל מחיקה
  ל-‎owner_archive‎ לנצח: "הוסף-מחק-חזור" היה לולאה שמגדילה מסד של
  500MB ושאין בכל הריפו קוד שמנקה.
- ההגבלות שכן קיימות תלויות במשתנה סביבה אחד, והאזהרה על היעדרו הגיעה
  ל-‎logger.warning‎ — פירור ב-Sentry, בחוצץ לוגים שנמחק.
- קוד הזמנה של 30 ביט שלא פג לעולם, ששווה קריאה וכתיבה על כל
  ההיסטוריה הפיננסית של המשפחה.
- טופס ההרשמה ענה בוודאות על "האם לכתובת הזאת יש כאן חשבון".
- סשן של עשר שנים ששינוי סיסמה לא ניתק.
- והלקוח הוא סינגלטון ברמת התהליך שלא אופס בין בקשות.
"""
import re
from pathlib import Path

import pytest

from backend import app as app_module
from backend.app import app, limiter

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_APP_SRC = (_ROOT / "backend/app.py").read_text(encoding="utf-8")
_DB_SRC = (_ROOT / "backend/supabase_config.py").read_text(encoding="utf-8")


def _migration(name):
    return (_ROOT / "backend/supabase/migrations" / name).read_text(encoding="utf-8")


# ─── ד1: כל מסלול כתיבה מוגבל ────────────────────────────────────────────────

_WRITE_ROUTES = [
    ('/api/transactions', 'POST'),
    ('/api/transactions/<tx_id>', 'PUT'),
    ('/api/transactions/<tx_id>', 'DELETE'),
    ('/api/categories', 'POST'),
    ('/api/categories/<cat_id>', 'PUT'),
    ('/api/categories/<cat_id>', 'DELETE'),
    ('/api/recurring/<template_id>', 'DELETE'),
    ('/api/recurring/<template_id>/sync', 'PUT'),
    ('/api/profile', 'PUT'),
    ('/api/family', 'PUT'),
    ('/api/family/settings', 'PUT'),
]


@pytest.mark.parametrize("path,method", _WRITE_ROUTES, ids=[f"{m} {p}" for p, m in _WRITE_ROUTES])
def test_every_write_route_has_a_ceiling(path, method):
    """אין כאן תרחיש אנושי שמתקרב לגבול — הוא קיים כדי שסקריפט לא יוכל
    למלא את המסד, ובעיקר לא את ‎owner_archive‎ שלא מתנקה מעצמו."""
    route = f'@app.route("{path}", methods=["{method}"])'
    assert route in _APP_SRC, f"המסלול {method} {path} לא נמצא — הבדיקה מיושנת"

    after = _APP_SRC[_APP_SRC.index(route):]
    decorators = after[:after.index("\ndef ")]

    assert "@limiter.limit" in decorators, f"{method} {path} בלי שום הגבלת קצב"


def test_the_csv_export_is_limited_too():
    """ייצוא הוא שאילתה כבדה על חודש שלם, ו-‎/month.csv‎ הוא GET שאפשר
    לפתוח בלולאה."""
    after = _APP_SRC[_APP_SRC.index('@app.route("/month.csv")'):]
    assert "@limiter.limit" in after[:after.index("\ndef ")]


# ─── ד1: המגברים ─────────────────────────────────────────────────────────────

def test_the_archive_has_a_retention_window():
    """הטריגר מעתיק כל מחיקה ל-‎owner_archive‎, ובכל הריפו לא היה שום
    קוד שמוחק משם. גם הבטחת המדיניות וגם מגבר ניצול."""
    sql = _migration("20260922160000_archive_retention.sql")

    assert "purge_expired_archive" in sql
    assert "interval '30 days'" in sql


def test_the_purge_is_scheduled_and_not_left_to_a_visitor():
    """ניקוי שרץ רק כשמישהו נכנס נפסק בדיוק במקרה שהכי צריך אותו:
    חשבון שנמחק ואיש לא חוזר אליו."""
    sql = _migration("20260922160000_archive_retention.sql")

    assert "cron.schedule" in sql
    assert "pg_cron" in sql


def test_bulk_category_insert_has_a_ceiling():
    """הרשימה הגיעה מגוף הבקשה בלי גבול — ~100,000 שורות תחת תקרת
    8MB — ו-‎_validated_category‎ סורק אותה ליניארית בכל כתיבת עסקה."""
    assert "_MAX_CATEGORIES_PER_FAMILY" in _DB_SRC

    fn = _DB_SRC[_DB_SRC.index("def bulk_add_categories("):]
    fn = fn[:fn.index("\ndef ")]
    assert "_MAX_CATEGORIES_PER_FAMILY" in fn


def test_the_recurring_engine_bounds_how_many_templates_it_expands():
    """תקרת 500 המופעים היא **לכל תבנית**. 1,000 תבניות הן חצי מיליון
    שורות ב-‎insert‎ אחד, בתוך worker אחד מתוך ארבעה."""
    fn = _DB_SRC[_DB_SRC.index("def materialize_recurring("):]
    fn = fn[:fn.index("\ndef ")]

    assert "_MAX_RECURRING_TEMPLATES" in fn


# ─── ד2: ההגבלות אומרות אם הן בכלל פועלות ────────────────────────────────────

def test_losing_the_shared_store_is_an_event_and_not_a_breadcrumb():
    """‎warning‎ אינו אירוע ב-Sentry, והלוג של Railway נמחק. בלי זה
    ההתראה היחידה על כך שכל ההגבלות נחלשו פי 4 לא הגיעה לאף אחד."""
    block = _APP_SRC[_APP_SRC.index("RATELIMIT_IS_SHARED"):][:600]

    assert "logger.error(" in block
    assert "logger.warning(" not in block


def test_health_says_whether_the_limits_are_actually_shared():
    """אחרת אין שום דרך לבדוק חוץ מלחפש בלוגים של הפריסה."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        body = c.get("/health").get_json()

    assert "rate_limiting" in body
    assert body["rate_limiting"] in ("shared", "per-worker")


# ─── ד4: קוד ההזמנה פג ───────────────────────────────────────────────────────

def test_the_invite_code_expires():
    """32^6 הוא כמיליארד — סביר לקוד שמקריאים בטלפון, ולא סביר כשהוא
    תקף לנצח. קוד תקף שווה קריאה **וכתיבה** על כל ההיסטוריה."""
    sql = _migration("20260922180000_invite_code_expiry.sql")

    assert "invite_code_expires_at" in sql
    assert "interval '7 days'" in sql


def test_an_expired_code_looks_exactly_like_a_wrong_one():
    """אחרת התשובה עצמה מגלה שהקוד היה אמיתי פעם — בדיוק המידע שמנחש
    מחפש."""
    sql = _migration("20260922180000_invite_code_expiry.sql")
    join = sql[sql.index("function public.join_family_by_code"):]

    assert "invite_code_expires_at is null or invite_code_expires_at > now()" in join
    assert "return null" in join


def test_the_preview_respects_the_expiry_too():
    sql = _migration("20260922180000_invite_code_expiry.sql")
    preview = sql[sql.index("function public.family_name_for_code"):]

    assert "invite_code_expires_at" in preview


def test_settings_shows_when_the_code_stops_working():
    """בלי זה אין שום דרך לדעת שהקוד שאתה שולח בוואטסאפ כבר לא יעבוד."""
    html = (_ROOT / "frontend/templates/settings.html").read_text(encoding="utf-8")

    assert "invite_expired" in html
    assert "invite_expires_in" in html


@pytest.mark.parametrize("stamp,expired", [
    ("2020-01-01T00:00:00+00:00", True),
    ("2099-01-01T00:00:00+00:00", False),
    (None, False),
])
def test_the_expiry_check_compares_aware_datetimes(stamp, expired):
    """‎clock.now()‎ נטולת אזור בכוונה, ו-‎timestamptz‎ חוזר עם היסט.
    השוואה ביניהם מרימה ‎TypeError‎, כלומר עמוד ההגדרות היה קורס."""
    family = {"invite_code_expires_at": stamp} if stamp else {}

    assert app_module._invite_expired(family) is expired


# ─── ד5: הסינגלטון מאופס בין בקשות ───────────────────────────────────────────

def test_an_empty_token_resets_the_header_instead_of_leaving_it():
    """הלקוח הוא סינגלטון ברמת התהליך. ‎inject_auth‎ יצאה מוקדם כשאין
    סשן, כך שבקשה אנונימית נחתה על worker שעדיין נושא JWT קודם.

    לא נגיש היום — אף מסלול אנונימי לא פונה ל-PostgREST — אבל זו
    מלכודת שמחכה למסלול הציבורי הבא, ואותה דליפה בין משפחות שה-Procfile
    מזהיר מפניה בהקשר של חוטים."""
    fn = _DB_SRC[_DB_SRC.index("def set_auth_token("):]
    fn = fn[:fn.index("\ndef ")]

    assert "SUPABASE_KEY" in fn, "טוקן ריק לא מאפס את הכותרת"


def test_the_reset_does_not_create_a_client_that_did_not_exist():
    """איפוס לא אמור לפתוח חיבור: בקשה אנונימית בתהליך שעוד לא דיבר עם
    המסד לא נושאת שום טוקן ממילא."""
    fn = _DB_SRC[_DB_SRC.index("def set_auth_token("):]
    fn = fn[:fn.index("\ndef ")]

    assert "_client if not access_token else get_client()" in fn


def test_inject_auth_resets_when_there_is_no_session():
    block = _APP_SRC[_APP_SRC.index("def inject_auth():"):][:600]

    assert 'db.set_auth_token("")' in block


# ─── ד6: סשן נטוש נסגר, ושינוי סיסמה מנתק ────────────────────────────────────

def test_logout_is_post_only():
    """עם ‎SameSite=Lax‎, ‎<img src=".../logout">‎ באתר אחר הוציא מבקר
    מהחשבון ומחק לו את עוגיות המכשיר."""
    rule = next(r for r in app.url_map.iter_rules() if str(r) == "/logout")

    assert "GET" not in rule.methods


# ─── ד7: כשלים שהיו בלתי נראים ───────────────────────────────────────────────

def test_a_failed_receipt_upload_is_logged():
    """השגיאה נזרקה לפח לגמרי, והמכסה כבר נספרה: המשתמש רואה סריקה
    מוצלחת בלי תג קבלה, ואין שום עקבה שמסבירה למה."""
    block = _APP_SRC[_APP_SRC.index("if upload_err:"):][:400]

    assert "logger.error" in block


def test_an_unreachable_database_is_an_event():
    block = _APP_SRC[_APP_SRC.index("health: database unreachable") - 300:][:400]

    assert "logger.error" in block


# ─── ד8: נעילת תלויות ────────────────────────────────────────────────────────

def test_the_transitive_dependencies_are_pinned():
    """‎requirements.txt‎ מקבע רק את מה שנבחר במפורש. postgrest, gotrue,
    pydantic ו-httpcore נפתרו מחדש בכל בנייה."""
    lock = (_ROOT / "requirements.lock")

    assert lock.exists(), "אין נעילה — כל תלות טרנזיטיבית נפתרת מחדש בכל בנייה"
    pins = [l for l in lock.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]
    assert len(pins) > 30
    assert all("==" in l for l in pins), "יש שורה בלי גרסה מקובעת"


def test_ci_scans_the_lockfile_and_not_only_the_direct_list():
    ci = (_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "pip-audit -r requirements.lock" in ci
