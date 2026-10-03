import os
import re

from dotenv import load_dotenv
from gotrue.errors import AuthApiError, AuthRetryableError
from postgrest.exceptions import APIError

from . import clock
from .money import format_money
from . import logs

logger = logs.get("smartfin.db")


class DataUnavailable(Exception):
    """השאילתה נכשלה — נזרקת במקום להחזיר ערך ריק שנראה כמו תשובה.

    זו הייתה התבנית המסוכנת ביותר בקוד הזה. פונקציה שנכשלה החזירה 0,
    רשימה ריקה או ‎False‎, והקורא לא יכול היה להבדיל בין "אין נתונים"
    לבין "לא הצלחתי לבדוק". התוצאה היא תשובה בטוחה ושגויה על המסך:

      · הסיכום החודשי נכשל  ← הדשבורד מציג ₪0 לכל התקציב. בלי סימן,
        בלי הודעה. המשתמש מסתכל על תקציב מאופס ומאמין לו. זו התקרית
        מאוגוסט 2026 — הסיבה הספציפית טופלה אז, ההתנהגות לא.
      · שליפת הקטגוריות נכשלת ← הדשבורד מסיק "משפחה חדשה" ושולח אותה
        לאשף ההרשמה; שם הבדיקה "כבר סיימת?" נכשלת גם היא ומחזירה
        "לא", והמשפחה נתקעת בין שני מסכים.
      · ספירת העסקאות נכשלת ← אישור נטישת המשפחה מדולג בשקט.
      · הגדרות המשפחה נכשלות ← ברירות המחדל של שיוך חוזרות, והעסקה
        נרשמת על שם של בן משפחה אחר.
      · מכסת הסריקות נכשלת ← ההגבלה על חשבון ה-OpenAI מפסיקה לעבוד.

    באג רגיל נראה על המסך. זה לא — ולכן אף אחד לא מדווח עליו.
    כישלון גלוי, שאפשר לנסות שוב אחריו, עדיף על מספר שקרי. וכבונוס:
    חריגה שלא נתפסת מגיעה ל-Sentry, בעוד ש-print נבלע בלוגים של Railway.
    """

load_dotenv()

_client = None


def get_client():
    global _client
    if _client is not None:
        return _client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        logger.warning("SUPABASE_URL or SUPABASE_KEY not set — running without database")
        return None

    try:
        from supabase import create_client
        _client = create_client(url, key)
        return _client
    except Exception:
        logger.exception("Failed to connect to Supabase")
        return None


def ping(timeout: float = 2.0) -> tuple:
    """בדיקת חיים למסד: נסיעה אחת הלוך-חזור עד Postgres וחזרה.
    מחזירה ‎(ok, detail)‎.

    לא עוברת דרך הלקוח המשותף, בכוונה. הלקוח הוא סינגלטון ברמת התהליך
    שכותרת ההרשאה שלו מוחלפת בכל בקשה (ראו set_auth_token), ובדיקת
    הבריאות היא בקשה לא מאומתת — שאילתה דרכו הייתה רצה עם הטוקן ששרד
    מהבקשה הקודמת ונכשלת ברגע שהוא פג. כישלון כזה נראה בדיוק כמו "המסד
    נפל", והוא לא. בקשה נפרדת עם מפתח ה-anon בודקת את מה שנשאל.

    השאילתה היא על טבלה אמיתית ולא על שורש ה-API, כדי שתשובה תקינה
    תעיד שגם Postgres עצמו ענה ולא רק ששער ה-API חי. RLS מחזירה רשימה
    ריקה למפתח האנונימי — וזה בסדר גמור: מה שנבדק הוא שהתשובה הגיעה,
    לא מה היה בה.
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return False, "not configured"
    try:
        import httpx
        r = httpx.get(
            f"{url.rstrip('/')}/rest/v1/families",
            params={"select": "id", "limit": "1"},
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=timeout,
        )
    except Exception as e:
        # בלי logger.exception: בזמן נפילה אמיתית זה נקרא כל דקה, וזה
        # היה מציף את Sentry באלף עותקים של אותה תקלה אחת.
        return False, type(e).__name__
    if r.status_code == 200:
        return True, "ok"
    return False, f"http {r.status_code}"


def set_auth_token(access_token: str):
    """Inject the user's JWT so RLS policies resolve auth.uid() correctly."""
    # ‎_client‎ ולא ‎get_client()‎: איפוס לא אמור **ליצור** לקוח. בקשה
    # אנונימית בתהליך שעוד לא דיבר עם המסד לא נושאת שום טוקן ממילא,
    # ויצירת לקוח בשבילה היא חיבור מיותר — ובבדיקות, פנייה אמיתית
    # ל-Supabase מתוך בדיקת יחידה.
    client = _client if not access_token else get_client()
    if not client:
        return
    if not access_token:
        # **חייב** לאפס, לא לצאת בשקט. הלקוח הוא סינגלטון ברמת התהליך,
        # ו-‎inject_auth‎ יוצאת מוקדם כשאין סשן — כך שבקשה אנונימית נוחתת
        # על worker שעדיין נושא את ה-JWT של המשתמש הקודם.
        #
        # היום זה לא נגיש: אף מסלול אנונימי לא פונה ל-PostgREST (‎ping‎
        # עוקף את הסינגלטון בכוונה, והתחברות/איפוס משתמשים ב-httpx ישיר).
        # אבל זו מלכודת שמחכה למסלול הציבורי הבא — ואותו סוג בדיוק של
        # דליפה בין משפחות שה-Procfile מזהיר מפניה בהקשר של חוטים.
        try:
            client.postgrest.auth(os.environ.get("SUPABASE_KEY", ""))
        except Exception:
            logger.exception("set_auth_token: reset")
        return

    try:
        client.postgrest.auth(access_token)
    except Exception:
        logger.exception("set_auth_token")


def _request_cache(key: str, loader):
    """מטמון-לבקשה על flask.g: נתונים יציבים בתוך בקשה אחת (קטגוריות, חברי
    משפחה, משפחה) נשלפים פעם אחת במקום 3-4 פעמים. מחוץ ל-Flask context
    (בדיקות/סקריפטים) — פשוט קורא ל-loader ישירות, בלי מטמון."""
    try:
        from flask import g, has_app_context
        if not has_app_context():
            return loader()
    except ImportError:
        return loader()
    cache = getattr(g, "_sf_cache", None)
    if cache is None:
        cache = g._sf_cache = {}
    if key not in cache:
        cache[key] = loader()
    return cache[key]


def _invalidate_family_cache(family_id: str):
    """מפנה את המטמון-לבקשה אחרי כתיבה לשורת המשפחה.

    בלי זה, קריאה שנעשית באותה בקשה *אחרי* הכתיבה מקבלת את הערך שנשלף
    לפניה. update_family_settings שולף את ההגדרות הקיימות כדי למזג לתוכן,
    וזה לבדו ממלא את המטמון בערך הישן — כך שהתשובה שחוזרת לדפדפן היא
    ההגדרות שלפני השינוי.

    הנזק לא נעצר בתצוגה: settings.js שומר את התשובה הזאת ומשתמש בה כדי
    להחליט אם להציג את בורר בן המשפחה במודאל העסקה. משתמש שהדליק "שיוך
    הוצאות" קיבל תשובה שאומרת שהוא כבוי, המודאל לא הציג בורר, והשרת —
    שקורא בבקשה הבאה את הערך הטרי — שייך כל עסקה למי שמחובר. שיוך שקט
    ושגוי של כסף, עד הרענון הבא.

    שני מטמונים נפרדים מחזיקים את הערך: זה שכאן, ו-g.family_settings
    ש-app.py מחזיק. שניהם נוקו כאן, אחרת הפינוי חלקי ולא מועיל."""
    try:
        from flask import g, has_app_context
        if not has_app_context():
            return
    except ImportError:
        return
    cache = getattr(g, "_sf_cache", None)
    if cache:
        cache.pop(f"family:{family_id}", None)
    g.pop("family_settings", None)


# ─── Auth ─────────────────────────────────────────────────────────────────────

def get_email_by_phone(normalized_phone: str):
    """מוצא את המייל המשויך למספר טלפון מנורמל (ספרות בלבד), עוד לפני
    שהמשתמש מחובר — דרך פונקציית ה-DB email_for_phone (SECURITY DEFINER,
    זמינה ל-anon). מחזיר None אם לא נמצא."""
    client = get_client()
    if not client or not normalized_phone:
        return None
    try:
        result = client.rpc("email_for_phone", {"p_phone": normalized_phone}).execute()
        return result.data or None
    except Exception:
        logger.exception("get_email_by_phone")
        return None


def sign_in(email: str, password: str):
    """Returns (user_data, error_message)."""
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        response = client.auth.sign_in_with_password({"email": email, "password": password})
        return response, None
    except Exception as e:
        return None, str(e)


def log_login_event(event: str = "login"):
    """מתעד כניסה לאתר בטבלה הפנימית login_events (לבעל האתר בלבד).
    לא-חוסם — כישלון בתיעוד לא מפריע להתחברות עצמה."""
    client = get_client()
    if not client:
        return
    try:
        client.rpc("log_login_event", {"p_event": event}).execute()
    except Exception:
        logger.exception("log_login_event")


def reset_transactions(family_id: str, only_user_id: str = None):
    """איפוס עסקאות: מוחק את כל עסקאות המשפחה (כולל תבניות קבועות), או —
    אם only_user_id סופק — רק את העסקאות המשויכות לאותו משתמש. כל שורה
    שנמחקת מארוכבת אוטומטית ב-owner_archive דרך הטריגר. Returns (deleted, err)."""
    client = get_client()
    if not client:
        return False, "Database not configured"
    try:
        query = client.table("transactions").delete().eq("family_id", family_id)
        if only_user_id:
            query = query.eq("user_id", only_user_id)
        # מספר השורות שנמחקו בפועל, ולא ‎True‎ קבוע: זו הפעולה ההרסנית
        # ביותר באפליקציה, והמשתמש צריך לראות כמה באמת נמחק.
        return len(query.execute().data or []), None
    except Exception as e:
        logger.exception("reset_transactions")
        return False, str(e)


def delete_my_account():
    """מחיקת החשבון של המשתמש המחובר לצמיתות (דרך פונקציית DB עם ארכוב פנימי).
    Returns (ok, error_message)."""
    client = get_client()
    if not client:
        return False, "Database not configured"
    try:
        client.rpc("delete_my_account", {}).execute()
        return True, None
    except Exception as e:
        logger.exception("delete_my_account")
        return False, str(e)


def sign_up(email: str, password: str, name: str, phone: str = None):
    """Returns (user_data, error_message)."""
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        response = client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"name": name, "phone": phone}}
        })
        return response, None
    except Exception as e:
        return None, str(e)


def refresh_session(refresh_token: str):
    """מחליפה refresh token בטוקן גישה טרי. מחזירה (response, error, fatal).

    ה-fatal הוא העיקר כאן: הוא מבדיל בין "השרת לא היה זמין לרגע" לבין
    "הטוקן נדחה". בלי ההבחנה הזאת כל בליפ רשת היה מנתק את המשתמש, וזה
    הורס את ההבטחה שנשארים מחוברים עד יציאה יזומה."""
    client = get_client()
    if not client:
        return None, "Database not configured", False
    try:
        response = client.auth.refresh_session(refresh_token)
        return response, None, False
    except AuthRetryableError as e:
        # תקלה זמנית (רשת, timeout) — שומרים על ההתחברות ומנסים שוב בבקשה הבאה
        return None, str(e), False
    except AuthApiError as e:
        # 5xx הוא תקלה אצלם, לא טוקן פסול. רק דחייה אמיתית מצדיקה ניתוק.
        transient = (e.status or 0) >= 500
        return None, str(e), not transient
    except Exception as e:
        # לא מזוהה — מניחים זמני. ניתוק שגוי גרוע יותר מבקשה אחת מנוונת.
        return None, str(e), False


# ─── Profile ──────────────────────────────────────────────────────────────────

# ‎PostgREST מחזיר את הקוד הזה כשהשאילתה הצליחה אבל לא החזירה שורות.
# זו תשובה תקפה, לא תקלה — וההבחנה הזאת היא לב העניין ב-fetch_profile.
_NO_ROWS = "PGRST116"


def fetch_profile(user_id: str):
    """מחזירה ‎(profile, ok)‎. ‎ok=False‎ פירושו **שהשליפה נכשלה** — לא שאין פרופיל.

    ההפרדה הזאת נראית פדנטית והיא לא. עד עכשיו כל חריגה חזרה כ-None, וזה
    לא הבדיל בין "למשתמש אין פרופיל" לבין "השרת לא ענה לשתי שניות".
    ensure_family הסיק מ-None שאין למשתמש משפחה, יצר לו אחת חדשה, ודרס את
    השיוך הקיים — כך שתקלת רשת חולפת בזמן התחברות ניתקה אותו לצמיתות מכל
    ההיסטוריה שלו, בלי שום מסלול חזרה מהממשק, בזמן שבן הזוג שלו נשאר
    במשפחה הישנה. משם והלאה השניים מזינים לשני תקציבים נפרדים בלי לדעת."""
    client = get_client()
    if not client:
        return None, False
    try:
        # שם הקשר מצוין במפורש. מאז שנוסף families.manager_id יש שני קשרים
        # בין הטבלאות — profiles.family_id→families ו-families.manager_id→profiles
        # — ו-PostgREST מסרב לנחש למי התכוונו (PGRST201). בלי זה השליפה
        # נכשלת, ומכיוון שהיא רצה בהתחברות, אף אחד לא מצליח להיכנס.
        result = client.table("profiles") \
            .select("*, families!profiles_family_id_fkey(name)") \
            .eq("id", user_id).single().execute()
        return result.data, True
    except APIError as e:
        if (e.json() or {}).get("code") == _NO_ROWS:
            return None, True          # אין פרופיל — תשובה, לא כישלון
        logger.exception("fetch_profile(%s)", user_id)
        return None, False
    except Exception:
        logger.exception("fetch_profile(%s)", user_id)
        return None, False


# ‎max_rows‎ של PostgREST (config.toml, ובלוח הבקרה בייצור): כל תשובה נחתכת
# באלף שורות — בלי שגיאה ובלי סימן שמשהו חסר.
_PAGE_SIZE = 1000


def _fetch_all(make_query) -> list:
    """כל השורות, בעמודים של ‎_PAGE_SIZE‎, עד עמוד קצר.

    ‎make_query‎ בונה את השאילתה מחדש לכל עמוד (בונה-השאילתות של
    PostgREST הוא בר-שינוי), והיא **חייבת** למיין לפי עמודה ייחודית —
    בלי סדר קבוע, עמודים יכולים לחפוף או לדלג על שורות."""
    rows, start = [], 0
    while True:
        page = make_query().range(start, start + _PAGE_SIZE - 1).execute().data or []
        rows.extend(page)
        if len(page) < _PAGE_SIZE:
            return rows
        start += _PAGE_SIZE


def export_account_data(family_id: str, user_id: str) -> dict:
    """כל מה שהאפליקציה מחזיקה על המשתמש ועל המשפחה שלו, במבנה אחד.

    ‎/month.csv‎ היה הייצוא היחיד — חודש בודד, מעמוד החודש, בלי פרופיל,
    בלי פרויקטים ובלי קטגוריות. כלומר סעיף 20 (ניידות) לא סופק בפועל:
    אי אפשר היה לקחת את הנתונים ולעזוב בלי לייצא חודש-חודש ביד.

    פרויקט אישי של בן משפחה אחר לא נכלל, בדיוק כמו בכל שאר האפליקציה:
    ייצוא אינו עוקף פרטיות בתוך המשפחה.
    """
    client = get_client()
    if not client or not family_id:
        raise DataUnavailable("export_account_data: no client")

    try:
        # בעמודים: עם 55 עסקאות בחודש, אלף הן שנה וחצי — ומשם הקובץ "המלא"
        # הכיל רק את האלף החדשות, וייראה שלם.
        transactions = _fetch_all(lambda: client.table("transactions")
                                  .select("*, categories(name), projects(name)")
                                  .eq("family_id", family_id)
                                  .order("date", desc=True)
                                  .order("id"))

        # פרויקטים אישיים של אחרים מוסתרים גם כאן
        visible_projects = {p["id"] for p in get_projects(family_id, user_id)}
        transactions = [
            t for t in transactions
            if not t.get("project_id") or t["project_id"] in visible_projects
        ]

        return {
            "exported_at": clock.now().isoformat(),
            "profile":     get_profile(user_id) or {},
            "family":      get_family(family_id) or {},
            "members":     get_family_members(family_id),
            "categories":  get_categories(family_id),
            "projects":    get_projects(family_id, user_id),
            "transactions": transactions,
        }
    except DataUnavailable:
        raise
    except Exception as e:
        logger.exception("export_account_data")
        raise DataUnavailable("export_account_data") from e


def get_profile(user_id: str):
    """הצורה הנוחה, לקוראים שעבורם "אין" ו"נכשל" שקולים (הצגת שם, אווטאר).
    מי שמקבל החלטה על סמך היעדר פרופיל חייב להשתמש ב-fetch_profile."""
    profile, _ = fetch_profile(user_id)
    return profile


def update_profile(user_id: str, name: str, phone: str = None, workplace: str = None):
    """Updates the current user's display name, phone and workplace.
    Returns (ok, error_message)."""
    client = get_client()
    if not client:
        return False, "Database not configured"
    try:
        client.table("profiles").update(
            {"name": name, "phone": phone, "workplace": workplace}
        ).eq("id", user_id).execute()
        return True, None
    except Exception as e:
        logger.exception("update_profile")
        if "duplicate" in str(e).lower() and "phone" in str(e).lower():
            return False, "מספר הטלפון כבר רשום בחשבון אחר"
        return False, None


def update_phone(user_id: str, phone: str):
    """מחליף רק את הטלפון (מתן, 1.10 — "חשבון" בהגדרות). מחזיר (ok, error)."""
    client = get_client()
    if not client:
        return False, "Database not configured"
    try:
        client.table("profiles").update({"phone": phone}).eq("id", user_id).execute()
        return True, None
    except Exception as e:
        logger.exception("update_phone")
        if "duplicate" in str(e).lower() and "phone" in str(e).lower():
            return False, "מספר הטלפון כבר רשום בחשבון אחר"
        return False, None


def _auth_user_request(method: str, access_token: str, **kwargs):
    """פנייה ל-‎/auth/v1/user‎ עם הטוקן של המשתמש עצמו — כמו ‎update_password‎,
    ולא דרך הלקוח המשותף, שה"סשן הנוכחי" שלו אינו בטוח בין משתמשים."""
    import httpx

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key or not access_token:
        return None
    return getattr(httpx, method)(
        f"{url}/auth/v1/user",
        headers={"apikey": key, "Authorization": f"Bearer {access_token}",
                 "Content-Type": "application/json"},
        timeout=10, **kwargs)


def get_auth_email(access_token: str):
    """המייל הנוכחי, ומייל שממתין לאישור אם יש: ‎(email, new_email)‎.

    המייל בסשן נשמר בהתחברות ולא מתעדכן לבד — אחרי שאישרו מייל חדש הוא
    נשאר הישן, והגדרות הציגו אותו ו"סיסמה נוכחית" נבדקה מולו ונכשלה.
    ‎(None, None)‎ כשאי אפשר לדעת; הקורא נופל למייל שבסשן."""
    import httpx
    try:
        r = _auth_user_request("get", access_token)
        if r is None or r.status_code >= 400:
            return None, None
        data = r.json()
        return data.get("email"), data.get("new_email")
    except (httpx.HTTPError, ValueError):
        logger.exception("get_auth_email")
        return None, None


def request_email_change(access_token: str, new_email: str, redirect_to: str):
    """מבקש להחליף את המייל. Supabase שולח קישור אישור לכתובת החדשה (ואם
    "שינוי מייל מאובטח" פעיל — גם לנוכחית), והמייל מתחלף רק אחרי האישור.
    עד אז ההתחברות ממשיכה עם הישן. מחזיר (ok, error)."""
    import httpx
    try:
        r = _auth_user_request("put", access_token, params={"redirect_to": redirect_to},
                               json={"email": new_email})
        if r is None:
            return False, "Database not configured"
        if r.status_code >= 400:
            body = r.json() if r.content else {}
            code = (body.get("error_code") or body.get("code") or "")
            text = (body.get("msg") or body.get("message") or "").lower()
            if code == "email_exists" or "already been registered" in text:
                return False, "המייל הזה כבר רשום בחשבון אחר"
            if "rate" in str(code) or "rate limit" in text:
                return False, "נשלחו יותר מדי מיילים — נסו שוב בעוד כמה דקות"
            logger.warning("request_email_change: %s %s", r.status_code, body)
            return False, None
        return True, None
    except (httpx.HTTPError, ValueError):
        logger.exception("request_email_change")
        return False, None


def update_workplace_history(user_id: str, family_id: str, new_workplace: str,
                             old_workplace: str, apply_to_all: bool):
    """מיישם שינוי מקום עבודה על עסקאות משכורת (הכנסה) קיימות של המשתמש —
    כדי ששינוי עתידי לא ישנה בשקט את מה שכבר מוצג על היסטוריה.

    apply_to_all=True: כל עסקאות המשכורת (עבר ועתיד) מקבלות את הערך החדש.
    apply_to_all=False: רק עסקאות מהחודש הנוכחי ואילך (לפי תאריך העסקה) מקבלות
    את הערך החדש; ישנות יותר שעוד אין להן תיעוד קפוא (workplace is null)
    מוקפאות לערך הישן, כדי שימשיכו להציג את מה שהציגו עד עכשיו."""
    client = get_client()
    if not client:
        return
    try:
        salary_cat_ids = [
            c["id"] for c in get_categories(family_id)
            if c.get("type") == "income" and "משכורת" in c.get("name", "")
        ]
        if not salary_cat_ids:
            return

        if apply_to_all:
            client.table("transactions").update({"workplace": new_workplace}) \
                .eq("user_id", user_id).eq("type", "income") \
                .in_("category_id", salary_cat_ids).execute()
            return

        month_start = clock.today().replace(day=1).isoformat()

        client.table("transactions").update({"workplace": old_workplace}) \
            .eq("user_id", user_id).eq("type", "income") \
            .in_("category_id", salary_cat_ids) \
            .is_("workplace", "null").lt("date", month_start).execute()

        client.table("transactions").update({"workplace": new_workplace}) \
            .eq("user_id", user_id).eq("type", "income") \
            .in_("category_id", salary_cat_ids) \
            .gte("date", month_start).execute()
    except Exception:
        logger.exception("update_workplace_history")


def update_password(access_token: str, new_password: str):
    """Updates the currently authenticated user's password.

    Calls the GoTrue REST API directly with the user's own access token
    rather than relying on the shared module-level client's implicit
    "current session" (which isn't safe to use for password changes in a
    multi-user server process — see set_auth_token for the same reasoning).
    """
    import httpx

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return False, "Database not configured"
    try:
        response = httpx.put(
            f"{url}/auth/v1/user",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"password": new_password},
            timeout=10,
        )
        if response.status_code >= 400:
            return False, response.json().get("msg", "עדכון הסיסמה נכשל")

        # מנתקים כל מכשיר **אחר**. בלי זה שינוי סיסמה לא עשה שום דבר
        # למי שכבר מחובר: הסשן של Flask חי 90 יום ומתחדש בכל בקשה,
        # וטוקן הרענון של Supabase ממשיך להחליף את עצמו — כלומר טלפון
        # גנוב, עוגייה שדלפה או מכשיר שנשאר אצל מישהו נשארים מחוברים,
        # ולמשתמש אין שום פעולה שמנתקת אותם.
        #
        # ‎scope=others‎ ולא ‎global‎: מי ששינה את הסיסמה לא אמור למצוא
        # את עצמו מנותק מהמכשיר שממנו עשה זאת.
        try:
            httpx.post(
                f"{url}/auth/v1/logout",
                params={"scope": "others"},
                headers={"apikey": key, "Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
        except Exception:
            # הסיסמה כבר הוחלפה — זה החלק שחייב להצליח. ניתוק שנכשל
            # נרשם ולא מבטל אותו.
            logger.exception("update_password: revoke other sessions")

        return True, None
    except Exception as e:
        return False, str(e)


def send_reset_email(email: str, redirect_to: str):
    """שולח מייל איפוס סיסמה עם קישור שחוזר לעמוד reset-password שלנו."""
    import httpx

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return False, "Database not configured"
    try:
        response = httpx.post(
            f"{url}/auth/v1/recover",
            params={"redirect_to": redirect_to},
            headers={"apikey": key, "Content-Type": "application/json"},
            json={"email": email},
            timeout=10,
        )
        if response.status_code >= 400:
            return False, response.json().get("msg", "שליחת המייל נכשלה")
        return True, None
    except Exception as e:
        return False, str(e)


def ensure_family(user_id: str, family_name: str = "המשפחה שלי"):
    """יוצרת משפחה ומשייכת אליה את המשתמש, אם אין לו כבר אחת.

    היצירה נעשית דרך ה-RPC ‎create_own_family‎ ולא בכתיבה ישירה, כי כתיבה
    ישירה ל-‎profiles.family_id‎ חסומה עכשיו ברמת ההרשאות: היא הייתה הדרך
    שבה משתמש מאומת יכול היה להעביר את עצמו למשפחה אחרת ולקרוא את כל
    הכספים שלה (ראו מיגרציה 20260916100000). הפונקציה נגזרת מ-auth.uid()
    ומסרבת להחליף משפחה קיימת, כך שהיא פותרת את הבעיה שלשמה היא קיימת
    בלי לפתוח אותה מחדש.

    היא גם פותרת את בעיית הביצה והתרנגולת שהייתה כאן: מדיניות הקריאה על
    families מתירה לקרוא משפחה רק אחרי שהפרופיל כבר מצביע עליה, ולכן
    היצירה והשיוך חייבים לקרות יחד — וכאן הם באמת אטומיים.
    """
    client = get_client()
    if not client:
        return None

    profile, ok = fetch_profile(user_id)
    if not ok:
        # השליפה נכשלה. אסור להסיק מזה שאין משפחה: יצירת משפחה כאן דורסת
        # את השיוך הקיים ומנתקת את המשתמש מכל ההיסטוריה שלו לצמיתות.
        # כישלון גלוי, שממנו אפשר להתאושש בניסיון הבא, עדיף בהרבה.
        logger.error("ensure_family(%s): profile read failed — refusing to create a family", user_id)
        return None
    if profile and profile.get("family_id"):
        return profile["family_id"]

    try:
        result = client.rpc("create_own_family", {"p_name": family_name}).execute()
        return result.data or None
    except Exception:
        logger.exception("ensure_family")
        return None


# ─── Family settings (העדפות משפחה) ──────────────────────────────────────────

# ברירות המחדל = ההתנהגות ההיסטורית של האתר. משפחה עם settings ריק מקבלת
# בדיוק את מה שהיה עד היום; רק מה שהמשפחה שינתה נשמר ב-DB.
DEFAULT_FAMILY_SETTINGS = {
    "owner_attribution": {"expense": True, "income": True, "savings": False},
    "anomaly": {"enabled": True, "percent": 150, "min_gap": 300},
    "show_workplace": True,
    # תקציב יעד לקטגוריה: ‎{"<category_id>": {"amount": 2000, "alert": true}}‎
    # קטגוריה שאינה כאן פשוט אין לה תקציב, וזו ברירת המחדל — אף אחת לא
    # מקבלת תקציב בלי שהמשפחה קבעה אותו.
    #
    # שתי החלטות נפרדות בכוונה: יש משפחות שרוצות לראות "₪1,800 מתוך
    # ₪2,000" בלי שהאפליקציה תנדנד להן על זה.
    "limits": {},
}


def category_budget(settings: dict, category_id: str) -> dict:
    """התקציב של קטגוריה, או None אם אין לה.

    מחזיר ‎{"amount": float, "alert": bool}‎."""
    entry = ((settings or {}).get("limits") or {}).get(str(category_id))
    if not isinstance(entry, dict):
        return None
    try:
        amount = float(entry.get("amount") or 0)
    except (TypeError, ValueError):
        return None
    if amount <= 0:
        return None
    return {"amount": amount, "alert": bool(entry.get("alert", True))}


def category_month_spent(family_id: str, category_id: str, year: int, month: int) -> float:
    """כמה יצא החודש על קטגוריה — הוצאות הבית בלבד (בלי פרויקטים), כמו
    הפס של התקציב בעמוד החודש. בשביל "עברתם את התקציב" בהוספה (רעיון 17).
    זורקת DataUnavailable."""
    import calendar
    client = get_client()
    if not client:
        raise DataUnavailable("category_month_spent: no client")
    first = f"{year:04d}-{month:02d}-01"
    last = f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
    try:
        rows = client.table("transactions").select("amount") \
            .eq("family_id", family_id).eq("type", "expense").eq("category_id", category_id) \
            .is_("project_id", "null").gte("date", first).lte("date", last).execute().data or []
    except Exception as e:
        raise DataUnavailable("category_month_spent") from e
    return round(sum(float(r["amount"]) for r in rows), 2)


def apply_budgets(breakdown: list, settings: dict) -> list:
    """מוסיף לכל שורת פילוח את מצב התקציב שלה, אם יש.

    ‎budget‎ = הסכום, ‎budget_pct‎ = כמה נוצל (יכול לעבור 100),
    ‎budget_left‎ = כמה נשאר (שלילי בחריגה), ‎budget_over‎ = האם חרג.

    הפס הקיים מודד כמה הקטגוריה מתוך סך ההוצאות החודש — כלומר "מכולת
    היא 35% מההוצאות", לא "נשאר ₪200". עם תקציב הוא מודד מול ההחלטה
    של המשפחה, וזה מה שבאמת שואלים."""
    out = []
    for row in breakdown:
        budget = category_budget(settings, row.get("category_id"))
        row = dict(row)
        if budget:
            spent = float(row.get("total") or 0)
            row["budget"]       = budget["amount"]
            row["budget_alert"] = budget["alert"]
            row["budget_pct"]   = min(round(spent / budget["amount"] * 100), 100)
            row["budget_left"]  = round(budget["amount"] - spent, 2)
            row["budget_over"]  = spent > budget["amount"]
            # החריגה עצמה, כדי שהתצוגה לא תחשב שוב
            row["budget_excess"] = round(max(spent - budget["amount"], 0), 2)
        out.append(row)
    return out


# מפתחות שהערך שלהם הוא **מפה שלמה**, ולכן מוחלפים ולא מתמזגים.
#
# ‎limits‎ ממופה לפי מזהה קטגוריה, וכשמסירים תקציב הוא פשוט נעדר מהמפה
# החדשה. מיזוג ב-‎.update()‎ יכול רק להוסיף או לדרוס מפתחות — לעולם לא
# למחוק — אז ההסרה לא נשמרה מעולם: המסך הראה תקציב כבוי, והשרת המשיך
# להחזיק אותו. שאר המפתחות המקוננים (owner_attribution, anomaly) הם
# רשומות עם שדות קבועים ונכון להמשיך למזג אותן.
# ‎member_colors‎ (סבב 6, פריט 13) — המפה המלאה נשלחת תמיד, ומי שעזב יוצא ממנה
_WHOLE_MAP_KEYS = frozenset({"limits", "member_colors"})


def _merge_settings(base: dict, patch: dict) -> dict:
    """מיזוג ברמה אחת של עומק — מפתחות מקוננים (owner_attribution, anomaly)
    מתמזגים במקום להימחק כשמעדכנים רק חלק מהם. ראו ‎_WHOLE_MAP_KEYS‎
    לחריגים שמוחלפים במלואם."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in (patch or {}).items():
        if k in _WHOLE_MAP_KEYS:
            out[k] = dict(v) if isinstance(v, dict) else v
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def get_family_settings(family_id: str) -> dict:
    """ההגדרות האפקטיביות של משפחה: ברירות מחדל + מה שנשמר ב-DB."""
    stored = (get_family(family_id) or {}).get("settings") or {}
    return _merge_settings(DEFAULT_FAMILY_SETTINGS, stored)


def update_family_settings(family_id: str, patch: dict) -> bool:
    """ממזג עדכון חלקי לתוך ההגדרות השמורות של המשפחה.

    המיזוג נעשה **במסד**, במשפט אחד עם ‎for update‎, ולא כאן. קודם זה היה
    קרא-מזג-כתוב בלי שום נעילה: ארבעה workers, שורה אחת, ושני בני משפחה
    ששמרו הגדרות באותה שנייה דרסו זה את זה. מי שקבע תקציב וקיבל "נשמר"
    ראה אותו נעלם ברענון הבא, ובלי שום סימן שמשהו קרה.

    הסמנטיקה זהה ל-‎_merge_settings‎ (עומק אחד + ‎_WHOLE_MAP_KEYS‎), והיא
    נשלחת לפונקציה כדי ששני המימושים לא יוכלו להיפרד בשקט."""
    client = get_client()
    if not client or not family_id:
        return False
    try:
        client.rpc("merge_family_settings", {
            "p_family_id":  family_id,
            "p_patch":      patch or {},
            "p_whole_keys": sorted(_WHOLE_MAP_KEYS),
        }).execute()
        _invalidate_family_cache(family_id)
        return True
    except Exception:
        logger.exception("update_family_settings")
        return False


# ─── Receipt scanning (צילום קבלה) ────────────────────────────────────────────

RECEIPT_MONTHLY_LIMIT = 100

# תקרה על **סך** הסריקות של כל המשפחות יחד.
#
# המכסה שלמעלה היא לכל משפחה, וההרשמה פתוחה — כל חשבון חדש מקבל משפחה,
# ואיתה מכסה טרייה. כלומר לא הייתה שום תקרה על הסכום הכולל, והמסלול הזה
# הוא היחיד באפליקציה שעולה כסף אמיתי.
#
# יש גם תקרת חיוב בלוח הבקרה של OpenAI (הוגדרה 20.9.2026), והיא רשת
# הביטחון האחרונה. התקרה כאן קיימת כי היא נכשלת אחרת: בעברית, עם הצעה
# להזין ידנית, במקום שהמפתח ייחסם ותתקבל שגיאת API סתומה שנראית כמו באג.
#
# המספר: משפחה פעילה מאוד צורכת ~50 בחודש, אז 2,000 הן כ-40 משפחות
# בשימוש כבד — הרבה מעל כל שימוש אמיתי בהיקף הנוכחי, ועדיין בלם.
RECEIPT_GLOBAL_MONTHLY_LIMIT = int(os.environ.get("RECEIPT_GLOBAL_MONTHLY_LIMIT", "2000"))

_RECEIPT_MEDIA_TYPES = ("image/jpeg", "image/png", "image/webp")


def _month_start() -> str:
    """תחילת החודש בשעון ישראל. משותף לשתי הספירות, כדי ששתיהן
    יתאפסו באותו רגע — השרת עצמו רץ ב-UTC.

    עם אזור הזמן במפורש: ‎"2026-10-01"‎ לבד פורש במסד (UTC) כחצות UTC,
    שהיא 03:00 בישראל בקיץ — וסריקה ב-01:30 ב-1 לחודש נספרה לחודש הקודם."""
    from datetime import datetime
    today = clock.today()
    return datetime(today.year, today.month, 1, tzinfo=clock.ISRAEL).isoformat()


def receipt_scans_globally_this_month() -> int:
    """כמה סריקות בוצעו החודש בכל המשפחות יחד.

    דרך RPC ולא דרך שאילתה: RLS על ‎receipt_scans‎ מגבילה כל משתמש
    למשפחה שלו, אז ספירה רגילה הייתה מחזירה את שלו בלבד — כלומר תקרה
    שלעולם לא נחצית. הפונקציה מחזירה מספר אחד ותו לא."""
    client = get_client()
    if not client:
        raise DataUnavailable("receipt_scans_globally_this_month: no client")
    try:
        return client.rpc("receipt_scans_global_since",
                          {"p_since": _month_start()}).execute().data or 0
    except Exception as e:
        # כמו בספירה לכל משפחה: 0 פירושו "אין ניצול", כלומר ביטול ההגבלה
        raise DataUnavailable("receipt_scans_globally_this_month") from e


def receipt_scans_this_month(family_id: str) -> int:
    """כמה סריקות מוצלחות בוצעו החודש — סריקות שנכשלו לא נרשמות ולא נספרות."""
    client = get_client()
    if not client or not family_id:
        return 0
    try:
        result = client.table("receipt_scans").select("id", count="exact") \
            .eq("family_id", family_id).gte("created_at", _month_start()).execute()
        return result.count or 0
    except Exception as e:
        # 0 פירושו "לא נוצלה מכסה" — כלומר ההגבלה על ההוצאה מפסיקה לעבוד
        raise DataUnavailable("receipt_scans_this_month") from e


def record_receipt_scan(family_id: str, user_id: str):
    """רושם סריקה מוצלחת לצורך מכסת RECEIPT_MONTHLY_LIMIT."""
    client = get_client()
    if not client:
        return
    try:
        client.table("receipt_scans").insert(
            {"family_id": family_id, "user_id": user_id}, returning="minimal"
        ).execute()
    except Exception:
        logger.exception("record_receipt_scan")


def upload_receipt(access_token: str, family_id: str, image_bytes: bytes, content_type: str):
    """מעלה תמונת קבלה לתיקיית המשפחה ב-bucket הפרטי 'receipts'.
    נעשה עם ה-JWT של המשתמש (לא מפתח השירות) כדי ש-RLS יאמת לפי המשפחה שלו.
    Returns (storage_path, error)."""
    import httpx, uuid as _uuid

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return None, "Database not configured"

    ext  = "jpg" if content_type == "image/jpeg" else content_type.split("/")[-1]
    path = f"{family_id}/{_uuid.uuid4()}.{ext}"
    try:
        response = httpx.post(
            f"{url}/storage/v1/object/receipts/{path}",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {access_token}",
                "Content-Type": content_type,
            },
            content=image_bytes,
            timeout=20,
        )
        if response.status_code >= 400:
            return None, "העלאת הקבלה נכשלה"
        return path, None
    except Exception as e:
        return None, str(e)


def get_receipt_signed_url(access_token: str, path: str):
    """קישור זמני (5 דקות) לצפייה בתמונת קבלה. Returns (url, error)."""
    import httpx

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return None, "Database not configured"
    try:
        response = httpx.post(
            f"{url}/storage/v1/object/sign/receipts/{path}",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"expiresIn": 300},
            timeout=10,
        )
        if response.status_code >= 400:
            return None, "לא ניתן להציג את הקבלה"
        signed = response.json().get("signedURL")
        return f"{url}/storage/v1{signed}", None
    except Exception as e:
        return None, str(e)


def delete_receipt(access_token: str, path: str):
    """מוחקת קובץ קבלה מהאחסון (למשל כשמוחקים את העסקה המצורפת)."""
    delete_receipts(access_token, [path])


def delete_receipts(access_token: str, paths) -> None:
    """מוחקת כמה קבצי קבלה בבקשה אחת, בשם המשתמש (מדיניות האחסון: רק מי
    שבמשפחה של התיקייה).

    אין ניקוי לילי שיאסוף אחריה: ‎purge_orphan_receipts‎ נכשלה בכל ריצה
    (Supabase חוסמת מחיקה ישירה מטבלאות האחסון) והוסרה ב-20260929150000.
    אז מחיקה של עסקאות חייבת לקחת איתה את הקבצים שלה כאן, ברגע המחיקה."""
    import httpx

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    paths = sorted({p for p in (paths or []) if p})
    if not url or not key or not paths:
        return
    for i in range(0, len(paths), 100):
        try:
            httpx.request(
                "DELETE",
                f"{url}/storage/v1/object/receipts",
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"prefixes": paths[i:i + 100]},
                timeout=10,
            )
        except Exception:
            logger.exception("delete_receipts")


def receipt_paths(family_id: str, project_ids=None, user_id: str = None) -> list:
    """נתיבי הקבלות של עסקאות שעומדות להימחק: בפרויקטים האלה, ו/או של
    המשתמש הזה. נאסף **לפני** המחיקה — אחריה אין שורה שמצביעה על הקובץ."""
    client = get_client()
    if not client or not (project_ids or user_id):
        return []
    try:
        out = []
        if project_ids:
            out += _fetch_all(lambda: client.table("transactions").select("id, receipt_path")
                              .eq("family_id", family_id).in_("project_id", list(project_ids))
                              .not_.is_("receipt_path", "null").order("id"))
        if user_id:
            out += _fetch_all(lambda: client.table("transactions").select("id, receipt_path")
                              .eq("family_id", family_id).eq("user_id", user_id)
                              .not_.is_("receipt_path", "null").order("id"))
        return sorted({r["receipt_path"] for r in out if r.get("receipt_path")})
    except Exception:
        # בלי הנתיבים אין מה למחוק — אבל המחיקה עצמה לא נעצרת בגלל קבצים
        logger.exception("receipt_paths")
        return []


def personal_project_ids(family_id: str, owner_id: str) -> list:
    """הפרויקטים האישיים של בן משפחה — כדי לדעת מה יימחק כשהוא יוצא."""
    client = get_client()
    if not client:
        raise DataUnavailable("personal_project_ids: no client")
    try:
        return [r["id"] for r in client.table("projects").select("id")
                .eq("family_id", family_id).eq("owner_id", owner_id).execute().data or []]
    except Exception as e:
        raise DataUnavailable("personal_project_ids") from e


def receipts_in_use(family_id: str, paths) -> set:
    """אילו מהקבצים האלה עסקה כלשהי עדיין מצביעה עליהם. נקרא **אחרי**
    מחיקת עסקאות: מה שחוזר כאן — לא מוחקים. חריגה, לא "אף אחד"."""
    paths = sorted({p for p in (paths or []) if p})
    if not paths:
        return set()
    client = get_client()
    if not client:
        raise DataUnavailable("receipts_in_use: no client")
    try:
        rows = client.table("transactions").select("receipt_path") \
            .eq("family_id", family_id).in_("receipt_path", paths).execute().data
        return {r["receipt_path"] for r in rows}
    except Exception as e:
        raise DataUnavailable("receipts_in_use") from e


def receipt_in_use(path: str, family_id: str) -> bool:
    """האם עסקה כלשהי מצביעה על הקובץ. חריגה — לא "לא": מחיקה של קובץ
    שבשימוש משאירה עסקה עם קבלה שבורה."""
    client = get_client()
    if not client:
        raise DataUnavailable("receipt_in_use: no client")
    try:
        return bool(client.table("transactions").select("id")
                    .eq("family_id", family_id).eq("receipt_path", path)
                    .limit(1).execute().data)
    except Exception as e:
        raise DataUnavailable("receipt_in_use") from e


def transaction_links(tx_id: str, family_id: str):
    """השיוכים של עסקה קיימת — בעלים ופרויקט — או ‎None‎ אם אינה קיימת.

    בשביל העריכה: בדיקות השרת על בעלים ועל פרויקט נועדו לבחירה **חדשה**,
    ודחו גם ערך שלא השתנה — עסקה של מי שעזב, או בפרויקט שהפסיק לעקוב אחרי
    הסוג. הטופס "פתר" את זה בכך שהחליף את הערך בשקט."""
    client = get_client()
    if not client:
        raise DataUnavailable("transaction_links: no client")
    try:
        # גם הערכים עצמם — ל"בטל" אחרי עריכה (‎if_match‎ ב-app.py)
        rows = client.table("transactions").select(
            "user_id, project_id, amount, type, date, description, category_id, project_category_id") \
            .eq("id", tx_id).eq("family_id", family_id).limit(1).execute().data or []
    except Exception as e:
        raise DataUnavailable("transaction_links") from e
    return rows[0] if rows else None


def transaction_meta(tx_id: str, family_id: str):
    """מי הזין ומתי — לשורה בתחתית חלון העריכה (מתן, 3.10 — רעיון 22).
    ‎None‎ אם העסקה לא נמצאה. זורקת DataUnavailable."""
    client = get_client()
    if not client:
        raise DataUnavailable("transaction_meta: no client")
    try:
        rows = client.table("transactions").select("created_by, created_at, recurring_parent_id") \
            .eq("id", tx_id).eq("family_id", family_id).limit(1).execute().data or []
    except Exception as e:
        raise DataUnavailable("transaction_meta") from e
    return rows[0] if rows else None


def get_transaction_receipt_path(transaction_id: str, family_id: str):
    client = get_client()
    if not client:
        return None
    try:
        result = client.table("transactions").select("receipt_path") \
            .eq("id", transaction_id).eq("family_id", family_id).single().execute()
        return (result.data or {}).get("receipt_path")
    except Exception:
        # None פירושו "אין קבלה", וכישלון שליפה נראה בדיוק כמו עסקה בלי
        # קבלה. הכיוון בטוח (לא נמחק כלום, לא מוצג כלום), אבל בלי הרישום
        # הזה אין שום זכר לכך שהייתה תקלה.
        logger.exception("get_transaction_receipt_path")
        return None


def scan_receipt(image_bytes: bytes, content_type: str, category_names: list):
    """שולח תמונת קבלה ל-OpenAI (מודל ראייה) ומחלץ סכום, בית עסק, תאריך וקטגוריה
    מוצעת מתוך קטגוריות ההוצאות של המשפחה בלבד. Returns (data_dict, error)."""
    import base64
    import json

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, "סריקת קבלות אינה מוגדרת בשרת"

    try:
        from openai import OpenAI
    except ImportError:
        return None, "סריקת קבלות אינה זמינה כרגע"

    media_type = content_type if content_type in _RECEIPT_MEDIA_TYPES else "image/jpeg"
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    category_prop = {"type": "string", "description": "השאר ריק אם אין התאמה ברורה."}
    if category_names:
        category_prop["enum"] = category_names

    tool = {
        "type": "function",
        "function": {
            "name": "extract_receipt",
            "description": "מחלץ מתמונת קבלה ישראלית את הסכום, שם בית העסק, התאריך והקטגוריה המתאימה.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "הסכום הכולל ששולם, מספר בלבד. אם התמונה אינה קבלה קריאה, החזר 0.",
                    },
                    "merchant": {
                        "type": "string",
                        "description": "שם בית העסק כפי שמופיע בקבלה.",
                    },
                    "date": {
                        "type": "string",
                        "description": "תאריך העסקה בפורמט YYYY-MM-DD. השאר ריק אם לא ברור.",
                    },
                    "category_name": category_prop,
                },
                "required": ["amount", "merchant"],
            },
        },
    }

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=300,
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": "extract_receipt"}},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "זו תמונה של קבלה ישראלית. חלץ ממנה את הנתונים באמצעות הכלי."},
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
                ],
            }],
        )
        tool_calls = response.choices[0].message.tool_calls
        if tool_calls:
            try:
                data = json.loads(tool_calls[0].function.arguments or "{}")
            except (TypeError, ValueError):
                data = {}
            try:
                amount = float(data.get("amount") or 0)
            except (TypeError, ValueError):
                amount = 0
            if amount <= 0:
                return None, "לא הצלחנו לקרוא את הקבלה — נסו שוב או הזינו ידנית"
            return {
                "amount":         amount,
                "merchant":       (data.get("merchant") or "").strip(),
                "date":           (data.get("date") or "").strip() or None,
                "category_name":  (data.get("category_name") or "").strip() or None,
            }, None
        return None, "לא הצלחנו לקרוא את הקבלה — נסו שוב או הזינו ידנית"
    except Exception:
        logger.exception("scan_receipt")
        return None, "שגיאה בסריקת הקבלה — נסו שוב"


# ─── Transactions ─────────────────────────────────────────────────────────────

def get_monthly_summary(family_id: str, year: int, month: int) -> dict:
    """Returns totals for income, expense, savings for a given month."""
    client = get_client()
    if not client:
        return _empty_summary()
    try:
        # עסקאות המשויכות לפרויקט לא נכללות במאזן החודשי — פרויקט הוא הוצאה/
        # הכנסה חד-פעמית/הונית שמעוותת את תמונת ה"חודש הרגיל" (מוצגות בנפרד).
        result = client.table("transactions") \
            .select("type, amount") \
            .eq("family_id", family_id) \
            .is_("project_id", "null") \
            .gte("date", f"{year}-{month:02d}-01") \
            .lt("date", _next_month(year, month)) \
            .execute()

        # אותו חישוב בדיוק כמו עמוד החודש. כאן הוא היה עותק בלי עיגול, ושברים
        # עשרוניים הפכו אפס ל-‎-1.1e-13‎ — ודף הבית הציג "-₪0" באדום.
        return summary_from_rows(result.data)
    except Exception as e:
        # לא מחזירים אפסים: דשבורד של ₪0 נראה כמו תקציב ריק ולא כמו תקלה
        raise DataUnavailable("get_monthly_summary") from e


_WEEK_LABELS = ("א׳", "ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "ש׳")


def week_spending(family_id: str, today=None, offset: int = 0) -> dict:
    """כרטיס "השבוע" בדף הבית (מתן, 30.9): הוצאות מראשון עד שבת, יום-יום.

    הוצאות הבית בלבד — בלי פרויקטים, ובלי עסקאות קבועות (תבנית או מופע):
    שכר דירה של ₪5,500 ביום אחד היה מגמד את כל השאר, והשבוע אמור להראות
    את ההוצאות השוטפות. ‎last_week‎ — אותו טווח בשבוע שעבר (ראשון עד אותו יום
    בשבוע), כדי שיום רביעי לא יושווה לשבוע שלם; ‎None‎ כשאין אז נתונים."""
    from datetime import timedelta
    today = today or clock.today()
    # ‎offset‎ — כמה שבועות אחורה (מתן, 2.10: דפדוף לשבועות קודמים). שבוע
    # שעבר מוצג שלם, ומושווה לשבוע השלם שלפניו.
    start = today - timedelta(days=(today.weekday() + 1) % 7) - timedelta(days=7 * offset)
    prev_start = start - timedelta(days=7)
    prev_end = (today - timedelta(days=7)) if offset == 0 else (start - timedelta(days=1))
    empty = {"days": [], "total": 0.0, "last_week": None, "diff": None,
             "offset": offset, "has_older": False}
    client = get_client()
    if not client:
        return empty
    try:
        rows = client.table("transactions") \
            .select("amount, date, description, category_id, is_recurring, recurring_parent_id, "
                    "project_id, categories(name, icon)") \
            .eq("family_id", family_id).eq("type", "expense").is_("project_id", "null") \
            .gte("date", prev_start.isoformat()) \
            .lte("date", (start + timedelta(days=6)).isoformat()).execute().data or []
    except Exception as e:
        raise DataUnavailable("week_spending") from e

    rows = [r for r in rows if not r.get("project_id")
            and not r.get("is_recurring") and not r.get("recurring_parent_id")]
    days = []
    for i in range(7):
        d = start + timedelta(days=i)
        txs = [r for r in rows if str(r["date"])[:10] == d.isoformat()]
        days.append({
            "date": d.isoformat(), "label": _WEEK_LABELS[i], "day": d.day, "month": d.month,
            "today": d == today, "future": d > today,
            "total": round(sum(float(r["amount"]) for r in txs), 2),
            "transactions": [{"icon": (r.get("categories") or {}).get("icon") or "📦",
                              "name": (r.get("categories") or {}).get("name") or _NO_CATEGORY,
                              "description": r.get("description") or "",
                              "amount": float(r["amount"])} for r in txs],
        })
    total = round(sum(d["total"] for d in days if not d["future"]), 2)
    prev = [r for r in rows if prev_start.isoformat() <= str(r["date"])[:10] <= prev_end.isoformat()]
    last = round(sum(float(r["amount"]) for r in prev), 2) if prev else None
    # היום שהפירוט שלו פתוח: היום עצמו בשבוע הנוכחי; בשבוע שעבר — היום האחרון
    # שהיו בו הוצאות (ואם לא היו — שבת)
    shown = [i for i, d in enumerate(days) if d["today"]] or \
            [i for i, d in enumerate(days) if d["total"]][-1:] or [6]
    for i, d in enumerate(days):
        d["selected"] = i == shown[0]
    # האם יש לאן לדפדף אחורה: הוצאה שוטפת כלשהי לפני תחילת השבוע הזה
    try:
        older = client.table("transactions").select("date") \
            .eq("family_id", family_id).eq("type", "expense").is_("project_id", "null") \
            .eq("is_recurring", False).is_("recurring_parent_id", "null") \
            .lt("date", start.isoformat()).order("date", desc=True).limit(1).execute().data or []
    except Exception as e:
        raise DataUnavailable("week_spending: older") from e
    return {"days": days, "total": total, "last_week": last,
            "diff": round(total - last, 2) if last is not None else None,
            "max": max([d["total"] for d in days] + [0]),
            "offset": offset, "has_older": bool(older)}


def _filter_hidden_personal_projects(rows: list, viewer_user_id: str) -> list:
    """מסנן שורות עסקה ששייכות לפרויקט אישי של בן משפחה אחר — פרטיות:
    רק בעל הפרויקט האישי רואה את העסקאות הבודדות שבו. לסיכומים החודשיים
    זה ממילא לא נוגע: הם מחריגים כל עסקת פרויקט (ראה _household_rows)."""
    if not viewer_user_id:
        return rows
    return [
        row for row in rows
        if not row.get("projects") or not row["projects"].get("owner_id")
           or row["projects"]["owner_id"] == viewer_user_id
    ]


def search_transactions(family_id: str, viewer_user_id: str, q: str,
                        settings: dict = None, limit: int = 100) -> dict:
    """חיפוש בכל החודשים (מתן, 30.9 — סבב 6, פריט 2).

    מחפש בתיאור, בשם הקטגוריה, במקום העבודה ובשם הפרויקט. מספר ("690") מוצא
    גם עסקאות בסכום הזה בדיוק. ההתאמה ב-Python ולא ב-PostgREST: שם הקטגוריה
    והפרויקט יושבים בטבלאות אחרות, ו-‎or‎ על עמודות של טבלה מקושרת לא נתמך.
    בהיקף של משפחה (אלפי שורות) זו שליפה אחת קלה.

    ‎count‎ ו-‎totals‎ — של כל מה שנמצא; ‎results‎ — עד ‎limit‎, מהחדש לישן."""
    empty = {"results": [], "count": 0, "truncated": False,
             "totals": {"expense": 0.0, "income": 0.0, "savings": 0.0}}
    needle = " ".join((q or "").split()).lower()
    amount = None
    try:
        amount = float(needle.replace(",", "").replace("₪", ""))
    except ValueError:
        pass
    if len(needle) < 2 and amount is None:
        return empty
    client = get_client()
    if not client:
        return empty
    try:
        rows = _fetch_all(lambda: client.table("transactions")
                          .select("*, categories(name, icon), project_categories(name, icon), "
                                  "profiles(name, workplace), projects(owner_id, name, icon)")
                          .eq("family_id", family_id)
                          .order("id"))
    except Exception as e:
        raise DataUnavailable("search_transactions") from e

    def hit(r):
        if amount is not None and abs(float(r.get("amount") or 0) - amount) < 0.005:
            return True
        cat = (r.get("project_categories") if r.get("project_category_id") else r.get("categories")) or {}
        text = " ".join(str(x) for x in (
            r.get("description"), r.get("workplace"), cat.get("name"),
            (r.get("projects") or {}).get("name")) if x).lower()
        return needle in text

    found = [r for r in _filter_hidden_personal_projects(rows, viewer_user_id) if hit(r)]
    found.sort(key=lambda r: (str(r.get("date") or ""), str(r.get("created_at") or "")), reverse=True)
    totals = {"expense": 0.0, "income": 0.0, "savings": 0.0}
    for r in found:
        if r.get("type") in totals:
            totals[r["type"]] += float(r.get("amount") or 0)
    return {"results": _format_transactions(found[:limit], settings),
            "count": len(found), "truncated": len(found) > limit,
            "totals": {k: round(v, 2) for k, v in totals.items()}}


def precheck_transaction(family_id: str, viewer_user_id: str, body: dict, today=None) -> dict:
    """מה לשאול לפני שמירה של עסקה חדשה (מתן, 30.9 — סבב 6, פריטים 6–7).

    ‎duplicate‎ — עסקה עם אותו סכום, סוג וקטגוריה, באותו יום או יום לפני/אחרי.
    הכי נפוץ: שני בני הזוג מזינים את אותה קנייה. ‎by‎ — רק כשמישהו אחר הזין.

    ‎unusual‎ — הסכום פי 5 ומעלה מהגדול בקטגוריה בחצי השנה האחרונה, כשיש
    לפחות 5 קודמות להשוות אליהן. לא בהכנסות: בונוס גדול הוא לא טעות.

    שתיהן שאלות ולא חסימות, ולכן כל תקלה כאן מחזירה "אין מה לשאול" — עדיף
    לשמור בלי אזהרה מאשר לא לשמור בכלל."""
    from datetime import date, datetime, timedelta
    none = {"duplicate": None, "unusual": None}
    today = today or clock.today()
    try:
        amount = float(body.get("amount"))
        type_ = str(body.get("type") or "")
        day = date.fromisoformat(str(body.get("date"))[:10])
    except (TypeError, ValueError):
        return none
    cat_key = "project_category_id" if body.get("project_category_id") else "category_id"
    cat = body.get(cat_key)
    if not cat or amount <= 0 or type_ not in ("expense", "income", "savings"):
        return none
    client = get_client()
    if not client:
        return none

    def same(r):
        return str(r.get(cat_key) or "") == str(cat)

    try:
        near = client.table("transactions").select("*, projects(owner_id)") \
            .eq("family_id", family_id).eq("type", type_) \
            .gte("date", (day - timedelta(days=1)).isoformat()) \
            .lte("date", (day + timedelta(days=1)).isoformat()).execute().data or []
        near = [r for r in _filter_hidden_personal_projects(near, viewer_user_id)
                if same(r) and abs(float(r.get("amount") or 0) - amount) < 0.005]
        duplicate = None
        if near:
            r = sorted(near, key=lambda x: str(x.get("created_at") or ""), reverse=True)[0]
            by = None
            if r.get("created_by") and r["created_by"] != viewer_user_id:
                by = next((m["name"] for m in get_family_members(family_id)
                           if m["id"] == r["created_by"]), None)
            time_ = None
            try:
                time_ = datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00")) \
                    .astimezone(clock.ISRAEL).strftime("%H:%M")
            except (KeyError, TypeError, ValueError):
                pass
            duplicate = {"amount": float(r["amount"]), "date": str(r["date"])[:10],
                         "description": r.get("description") or "", "by": by, "time": time_}

        unusual = None
        if type_ != "income":
            past = client.table("transactions").select("*, projects(owner_id)") \
                .eq("family_id", family_id).eq("type", type_) \
                .gte("date", (today - timedelta(days=183)).isoformat()).execute().data or []
            amounts = [float(r.get("amount") or 0)
                       for r in _filter_hidden_personal_projects(past, viewer_user_id) if same(r)]
            if len(amounts) >= 5 and amount >= 5 * max(amounts):
                unusual = {"min": round(min(amounts), 2), "max": round(max(amounts), 2)}
        return {"duplicate": duplicate, "unusual": unusual}
    except Exception:
        logger.exception("precheck_transaction")
        return none


_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")


def personal_project_owner(tx_id: str, family_id: str):
    """בעל הפרויקט האישי שהעסקה יושבת בו, או ‎None‎ (משפחתית, פרויקט
    משותף, או שהעסקה לא קיימת — אז המסלול עצמו יחזיר 404).

    הבסיס של ‎tx_visible_required‎ ב-app.py. RLS לא עוזרת כאן: היא
    מפרידה בין משפחות, ופרויקט אישי הוא פרטיות *בתוך* משפחה."""
    # מזהה שאינו UUID לא יתאים לאף שורה, והמסלול יחזיר עליו 404 בעצמו.
    # בלי הבדיקה, PostgREST דוחה אותו בשגיאה — והיא הייתה הופכת ל-503.
    if not _UUID_RE.match(str(tx_id)):
        return None
    client = get_client()
    if not client:
        raise DataUnavailable("personal_project_owner: no client")
    try:
        rows = client.table("transactions").select("project_id, projects(owner_id)") \
            .eq("id", tx_id).eq("family_id", family_id).limit(1).execute().data or []
    except Exception as e:
        # כשל כאן חייב לעצור, לא לעבור: "לא הצלחתי לבדוק" אינו "מותר"
        raise DataUnavailable("personal_project_owner") from e
    if not rows:
        return None
    return (rows[0].get("projects") or {}).get("owner_id")


def get_recent_transactions(family_id: str, limit: int = 5, settings: dict = None,
                            viewer_user_id: str = None) -> list:
    """Returns the most recent transactions with category and user info.

    עסקאות המשויכות לפרויקט מוחרגות — הן שייכות לפרויקט בלבד, ומופיעות בעמוד
    הפרויקט ובקטע "פרויקטים החודש". עקבי עם שאר נתוני החודש, שכולם מסננים
    אותן (סיכום, פילוח קטגוריות, חלוקה בין בני משפחה, השוואת חודשים)."""
    client = get_client()
    if not client:
        return []
    try:
        # מרווח ביטחון: אם יסוננו שורות פרטיות, עדיין נרצה להגיע ל-limit שורות גלויות
        fetch_limit = limit * 3 if viewer_user_id else limit
        # ממוין לפי סדר ההוספה (created_at) ולא לפי תאריך העסקה — כך עסקה שהוזנה
        # לאחרונה מופיעה ראשונה גם אם תוארכה לתאריך ישן (בקשת מתן)
        result = client.table("transactions") \
            .select("*, categories(name, icon), project_categories(name, icon), profiles(name, workplace), projects(owner_id, name, icon)") \
            .eq("family_id", family_id) \
            .is_("project_id", "null") \
            .order("created_at", desc=True) \
            .limit(fetch_limit) \
            .execute()
        rows = _filter_hidden_personal_projects(result.data, viewer_user_id)[:limit]
        return _format_transactions(rows, settings)
    except Exception as e:
        logger.exception("get_recent_transactions")
        raise DataUnavailable("get_recent_transactions") from e


def get_month_transactions(family_id: str, year: int, month: int, settings: dict = None,
                           viewer_user_id: str = None) -> list:
    """Returns all transactions for a given month (לא כולל עסקאות בפרויקט
    אישי של בן משפחה אחר — פרטיות)."""
    client = get_client()
    if not client:
        return []
    try:
        result = client.table("transactions") \
            .select("*, categories(name, icon), project_categories(name, icon), profiles(name, workplace), projects(owner_id, name, icon)") \
            .eq("family_id", family_id) \
            .gte("date", f"{year}-{month:02d}-01") \
            .lt("date", _next_month(year, month)) \
            .order("date", desc=True) \
            .execute()
        rows = _filter_hidden_personal_projects(result.data, viewer_user_id)
        return _format_transactions(rows, settings)
    except Exception as e:
        logger.exception("get_month_transactions")
        raise DataUnavailable("get_month_transactions") from e


def add_transaction(data: dict):
    """Inserts a transaction. data must include: amount, type, family_id, date."""
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        result = client.table("transactions").insert(data).execute()
        return result.data[0] if result.data else None, None
    except Exception as e:
        return None, str(e)


def get_recurring_transactions(family_id: str, viewer_user_id: str, settings: dict = None) -> list:
    """כל התבניות הקבועות שהצופה רשאי לראות.

    זה היה הקורא היחיד בלי ‎_filter_hidden_personal_projects‎: תשלום קבוע
    בפרויקט אישי הופיע לכל המשפחה בהגדרות ובעמוד החודש — תיאור, סכום
    ומזהה, ומהמזהה אפשר היה לערוך ולמחוק. ‎viewer_user_id‎ חובה בכוונה,
    כי המסנן פתוח כשהוא חסר."""
    client = get_client()
    if not client:
        return []
    try:
        result = client.table("transactions") \
            .select("*, categories(name, icon), project_categories(name, icon), "
                    "profiles(name, workplace), projects(owner_id, name, icon)") \
            .eq("family_id", family_id) \
            .eq("is_recurring", True) \
            .order("amount", desc=True) \
            .execute()
        return _format_transactions(
            _filter_hidden_personal_projects(result.data, viewer_user_id), settings)
    except Exception as e:
        logger.exception("get_recurring_transactions")
        raise DataUnavailable("get_recurring_transactions") from e


def is_active_template(row: dict, today=None) -> bool:
    """תבנית שתאריך הסיום שלה עבר כבר לא קבועה.

    כלל אחד לשני המסכים שמציגים "עסקאות קבועות". עד היום רק עמוד החודש
    סינן, וההגדרות הציגו גם סדרות שנגמרו — תחת הכותרת "N עסקאות חוזרות
    פעילות". אחרי "עדכן להבא" זה היה מציג את שכר הדירה פעמיים."""
    end = row.get("recurring_end_date")
    return not (end and str(end) < (today or clock.today()).isoformat())



_MAX_RECURRING_TEMPLATES = 200


def materialize_recurring(family_id: str) -> int:
    """משלים מופעים חסרים של עסקאות קבועות עד היום (כולל רטרואקטיבית).

    כל עסקה שסומנה כקבועה משמשת "תבנית": המופע הראשון הוא העסקה עצמה,
    ומכאן נוצרים מופעים רגילים (is_recurring=False) לפי התדירות, עד היום
    או עד תאריך הסיום. הפונקציה אידמפוטנטית — מופע שכבר קיים לא ייווצר שוב.
    מחזירה ‎(created, ok)‎. ‎ok=False‎ פירושו שהריצה נכשלה — וזה חשוב, כי
    הקורא מסמן "סונכרן להיום" ולא ינסו שוב עד מחר. כשל שנראה כהצלחה
    משאיר חודש בלי משכורת ובלי הוראות קבע עד למחרת."""
    from datetime import date

    client = get_client()
    if not client or not family_id:
        return 0, False
    try:
        # ‎limit‎ על התבניות. התקרה של 500 מופעים היא **לכל תבנית**, ואף
        # אחד לא הגביל כמה תבניות יש: 1,000 תבניות × 500 מופעים הוא
        # ‎insert‎ אחד של חצי מיליון שורות בתוך worker אחד, ואז OOM או
        # worker תקוע מתוך ארבעה. משפחה אמיתית מחזיקה עשרות.
        templates = client.table("transactions").select("*") \
            .eq("family_id", family_id).eq("is_recurring", True) \
            .limit(_MAX_RECURRING_TEMPLATES).execute().data
        if not templates:
            return 0, True

        # בעמודים: הרשימה היא של כל המשפחה. מעבר לאלף המנוע הפסיק לראות
        # חלק מהמופעים ויצר אותם שוב.
        existing = _fetch_all(lambda: client.table("transactions")
                              .select("recurring_parent_id, date")
                              .eq("family_id", family_id)
                              .not_.is_("recurring_parent_id", "null")
                              .order("id"))
        # תאריכי המופעים הקיימים לכל תבנית. לא סט של צמדי (תבנית, תאריך):
        # ההשוואה היא לפי תקופה ולא לפי תאריך מדויק, אחרת שינוי תאריך
        # בתבנית מייצר סדרה חדשה שכולה "חסרה" ומכפיל חודשים אחורה.
        have: dict = {}
        for r in existing:
            have.setdefault(r["recurring_parent_id"], set()).add(
                date.fromisoformat(str(r["date"])))

        # מטמון קטגוריות-משכורת ומקום-עבודה נוכחי לכל בעלים — נמנע שליפה
        # חוזרת לכל מופע, ומאפשר להקפיא workplace על מופעי משכורת קבועה
        # בדיוק כמו בהוספה ידנית (add_transaction)
        salary_cat_ids = {
            c["id"] for c in get_categories(family_id)
            if c.get("type") == "income" and "משכורת" in c.get("name", "")
        }
        workplace_by_user: dict = {}

        def _owner_workplace(uid):
            if uid not in workplace_by_user:
                profile = get_profile(uid) if uid else None
                workplace_by_user[uid] = (profile or {}).get("workplace")
            return workplace_by_user[uid]

        today = clock.today()
        new_rows = []
        for t in templates:
            is_salary = t.get("type") == "income" and t.get("category_id") in salary_cat_ids
            freq = t.get("recurring_frequency") or "monthly_1"
            seen = have.setdefault(t["id"], set())
            # שורת התבנית עצמה היא המופע הראשון (ראו התיעוד למעלה), אבל
            # אין לה recurring_parent_id ולכן היא לא נשלפה עם המופעים.
            # בלי זה תבנית שנפתחה ב-5 בינואר ועברה ל"ה-15 לחודש" מקבלת
            # מופע שני בינואר, לצד השורה המקורית.
            seen.add(date.fromisoformat(str(t["date"])))
            # מופעים שהמשתמש מחק במכוון. בלעדיהם המנוע רואה חור ומשלים
            # אותו — כלומר מחיקה של מופע בודד מתבטלת מעצמה למחרת, ומי
            # שביטל מנוי לחודש אחד רואה אותו חוזר בלי הסבר.
            for skipped in (t.get("recurring_skips") or []):
                seen.add(date.fromisoformat(str(skipped)))
            for d in _recurring_occurrences(t, today):
                if _already_materialized(freq, d, seen):
                    continue
                # המופע שנוצר עכשיו תופס את התקופה שלו, כדי ששני מופעים
                # מאותה תבנית באותה תקופה לא ייווצרו באותה ריצה
                seen.add(d)
                new_rows.append({
                    "amount":              t["amount"],
                    "type":                t["type"],
                    "date":                d.isoformat(),
                    "description":         t.get("description") or "",
                    "category_id":         t.get("category_id"),
                    # בלי אלה, מהחודש השני כל תשלום בתוך פרויקט נחת בהוצאות
                    # הבית כ"ללא קטגוריה" — לעסקת פרויקט אין קטגוריה משפחתית
                    "project_id":          t.get("project_id"),
                    "project_category_id": t.get("project_category_id"),
                    # מי שרשם את הסדרה — לא מי שבמקרה פתח את האפליקציה היום
                    # (בלי השדה, ברירת המחדל במסד היא ‎auth.uid()‎ של הריצה)
                    "created_by":          t.get("created_by"),
                    "user_id":             t.get("user_id"),
                    "family_id":           family_id,
                    "is_recurring":        False,
                    "recurring_parent_id": t["id"],
                    # נשמר גם על המופע (לא רק על התבנית) כדי שהתצוגה תוכל
                    # לציין "עסקה קבועה — כל X" בלי לשלוף את התבנית בנפרד
                    "recurring_frequency": t.get("recurring_frequency"),
                    "workplace":           _owner_workplace(t.get("user_id")) if is_salary else None,
                })

        created = 0
        if new_rows:
            try:
                client.table("transactions").insert(new_rows, returning="minimal").execute()
                created = len(new_rows)
            except Exception as e:
                # כשל ייחודיות פירושו שבקשה מקבילה כבר יצרה **חלק** מהמופעים.
                #
                # ‎insert‎ בודד הוא משפט אחד, אז שורה אחת מתנגשת מגלגלת אחורה
                # את כולן. ההנחה שהסיבה היחידה היא אצווה זהה לגמרי נכונה רק
                # בחפיפה מלאה: אם בקשה אחרת הספיקה ליצור את המשכורת ולא את
                # שכר הדירה, שתיהן נזרקות — ו-‎_sync_recurring‎ מסמן "סונכרן
                # להיום", כך שאף אחד לא ינסו שוב עד מחר. חודש שלם בלי שכר
                # דירה, בלי שום סימן.
                #
                # אז חוזרים שורה-שורה: מה שכבר קיים מדולג, והשאר נכנס.
                if "uq_tx_recurring_occurrence" not in str(e) and "23505" not in str(e):
                    raise
                for row in new_rows:
                    try:
                        client.table("transactions").insert(row, returning="minimal").execute()
                        created += 1
                    except Exception as one:
                        if "uq_tx_recurring_occurrence" in str(one) or "23505" in str(one):
                            continue    # מישהו אחר כבר יצר בדיוק את זה
                        raise
        # ‎created‎ ולא ‎len(new_rows)‎: אחרי נפילה חלקית המספרים שונים,
        # והקורא משתמש בזה כדי להחליט אם משהו באמת נוצר.
        return created, True
    except Exception:
        logger.exception("materialize_recurring")
        return 0, False


def _occurrence_period(freq: str, d):
    """מפתח התקופה של מופע. שני מופעים של אותה תבנית באותה תקופה הם אותה
    עסקה — גם אם התאריך שלהם שונה.

    בלי ההבחנה הזאת הדדופ השווה תאריכים מדויקים, ולכן שינוי תאריך בתבנית
    (למשל משכורת שעוברת מה-5 ל-10 לחודש) ייצר סדרת תאריכים חדשה שאף אחד
    ממנה לא היה מוכר — וכל החודשים אחורה נוצרו מחדש. משכורת של ₪14,000
    הוכפלה על שמונה חודשים בבת אחת, בכל מסך באפליקציה.

    לתדירות חודשית התקופה היא החודש הקלנדרי. לשבועית ודו-שבועית אין
    "תקופה" טבעית, אז נחשב מרחק של עד חצי צעד כאותו מופע שרק זז."""
    if freq in ("weekly", "biweekly"):
        return None                      # מטופל במרחק, ראו _already_materialized
    return (d.year, d.month)


def existing_occurrence_dates(tx_id: str, family_id: str):
    """התאריכים שהסדרה כבר "תפסה": המופעים שנוצרו והדילוגים. ‎None‎ אם
    העסקה עוד אינה תבנית קבועה — אז שום מופע שלה לא קיים.

    בשביל אזהרת המילוי-אחורה בעריכה: היא ספרה את כל המופעים מאז תחילת
    הסדרה, כולל אלה שכבר קיימים, ותיקון תיאור של משכורת ממרץ קיבל
    "הסדרה תיצור 6 עסקאות אחורה". המנוע מדלג על תקופה שכבר תפוסה
    (‎_already_materialized‎), אז גם הספירה חייבת."""
    from datetime import date
    client = get_client()
    if not client:
        raise DataUnavailable("existing_occurrence_dates: no client")
    try:
        rows = client.table("transactions").select("is_recurring, recurring_skips") \
            .eq("id", tx_id).eq("family_id", family_id).limit(1).execute().data or []
        if not rows or not rows[0].get("is_recurring"):
            return None
        instances = client.table("transactions").select("date") \
            .eq("recurring_parent_id", tx_id).eq("family_id", family_id) \
            .execute().data or []
    except Exception as e:
        raise DataUnavailable("existing_occurrence_dates") from e
    return [date.fromisoformat(str(r["date"])[:10]) for r in instances] + \
           [date.fromisoformat(str(d)[:10]) for d in (rows[0].get("recurring_skips") or [])]


def _already_materialized(freq: str, d, existing_dates) -> bool:
    """האם המופע הזה כבר קיים — לא לפי תאריך מדויק אלא לפי תקופה."""
    if freq in ("weekly", "biweekly"):
        tolerance = 3 if freq == "weekly" else 7
        return any(abs((d - e).days) <= tolerance for e in existing_dates)
    period = _occurrence_period(freq, d)
    return any(_occurrence_period(freq, e) == period for e in existing_dates)


def _recurring_occurrences(template: dict, until) -> list:
    """תאריכי המופעים של תבנית קבועה — אחרי תאריך המקור, עד 'until' (כולל)."""
    import calendar
    from datetime import date, timedelta

    start = date.fromisoformat(str(template["date"]))
    end_raw = template.get("recurring_end_date")
    end = date.fromisoformat(str(end_raw)) if end_raw else None
    freq = template.get("recurring_frequency") or "monthly_1"

    out = []
    if freq in ("monthly_1", "monthly_15", "monthly_same"):
        # monthly_same חוזר כל חודש ביום־בחודש של תאריך המקור (למשל ה-23);
        # monthly_1/15 קבועים ל-1 או ל-15
        target_day = {"monthly_1": 1, "monthly_15": 15}.get(freq, start.day)
        # מתחילים מחודש ההתחלה עצמו — מופע באותו חודש אחרי תאריך ההתחלה נחשב
        y, m = start.year, start.month
        while len(out) < 500:
            # קיצוץ ליום האחרון של החודש (למשל יום 31 בפברואר → 28/29)
            day = min(target_day, calendar.monthrange(y, m)[1])
            d = date(y, m, day)
            if d > until or (end and d > end):
                break
            if d > start:
                out.append(d)
            m += 1
            if m > 12:
                m, y = 1, y + 1
    else:
        step = timedelta(days=7 if freq == "weekly" else 14)
        d = start + step
        while d <= until and (not end or d <= end) and len(out) < 500:
            out.append(d)
            d += step
    return out


def projected_month_rows(family_id: str, year: int, month: int, today=None) -> list:
    """המופעים שהעסקאות הקבועות ייצרו בחודש שעוד לא הגיע (מתן, 30.9).

    חודש עתידי מוצג כמו כל חודש, עם מה שידוע עד כה — ומה שידוע הוא גם
    שכר הדירה של ה-1 בו. המופעים נוצרים כעסקאות אמיתיות רק כשהתאריך
    מגיע (‎materialize_recurring‎), ולכן בחודש הנוכחי ובחודשים שעברו אין
    מה להוסיף: שם הם כבר קיימים, והוספה הייתה סופרת אותם פעמיים.

    כל שורה היא העתק של התבנית בתאריך המופע, באותה צורה בדיוק כמו שורות
    החודש — כדי שכל הסיכומים והפילוחים יעברו עליה בלי מקרה מיוחד. היא
    מסומנת ‎projected‎: אין מאחוריה עסקה במסד, אז אין מה לערוך או למחוק."""
    import calendar
    from datetime import date
    today = today or clock.today()
    if (year, month) <= (today.year, today.month):
        return []
    client = get_client()
    if not client:
        return []
    try:
        templates = client.table("transactions") \
            .select("*, categories(name, icon), project_categories(name, icon), "
                    "profiles(name, workplace), projects(owner_id, name, icon)") \
            .eq("family_id", family_id) \
            .eq("is_recurring", True) \
            .execute().data or []
    except Exception as e:
        raise DataUnavailable("projected_month_rows") from e

    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    out = []
    for t in templates:
        for d in _recurring_occurrences(t, last):
            if d < first or d <= today:
                continue
            out.append({**t, "id": f"projected-{t['id']}-{d.isoformat()}",
                        "date": d.isoformat(), "is_recurring": False,
                        "recurring_parent_id": t["id"], "receipt_path": None,
                        "projected": True})
    return out


def update_transaction(transaction_id: str, family_id: str, data: dict):
    """Updates a transaction. Returns (updated_row, error)."""
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        result = client.table("transactions") \
            .update(data) \
            .eq("id", transaction_id) \
            .eq("family_id", family_id) \
            .execute()
        return (result.data[0] if result.data else None), None
    except Exception as e:
        return None, str(e)


def split_recurring_series(template_id: str, instance_id: str, family_id: str):
    """"עדכן להבא": מפצלת את הסדרה במופע שנערך. מחזירה (new_template_id, error).

    עד היום זה עדכן את שורת התבנית — אבל התבנית היא גם העסקה של החודש
    הראשון, אז "מהחודש הבא 5,500" הפך גם את ינואר ל-5,500. הפיצול עצמו,
    ולמה הוא נראה כך, מתועד במיגרציה ‎20260927120000_split_recurring_series‎.

    ‎(None, None)‎ = אין מה לפצל (המופע לא נמצא, לא של התבנית הזאת או של
    משפחה אחרת, או שהסדרה כבר נגמרה לפניו). המסלול מחזיר על זה 404."""
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        new_id = client.rpc("split_recurring_series", {
            "p_template_id": template_id,
            "p_instance_id": instance_id,
            "p_family_id":   family_id,
        }).execute().data
        return (new_id or None), None
    except Exception as e:
        logger.exception("split_recurring_series")
        return None, str(e)


def series_pivot(template_id: str, family_id: str, today=None):
    """עריכת עסקה קבועה מ"עסקאות קבועות" בהגדרות חלה מהחודש הנוכחי (מתן, 2.10).
    מחזירה מאיפה השינוי מתחיל:

    ‎("template", None)‎ — הסדרה התחילה בחודש הנוכחי או אחריו: אין עבר
        להגן עליו, עורכים את התבנית כרגיל.
    ‎("instance", (id, date))‎ — המופע האחרון שכבר נוצר בחודש הנוכחי.
    ‎("future", date)‎ — המופע של החודש עוד לא נוצר (משכורת ב-10, היום ה-2):
        התאריך הבא שלו.
    ‎("none", None)‎ — אין יותר מופעים (הסדרה נגמרה, או שהתבנית לא נמצאה).

    התבנית היא גם העסקה של החודש הראשון, ולכן עריכה שלה כתבה מחדש את
    ינואר. זה אותו באג ש"עדכון להבא" תיקן (‎split_recurring_series‎), רק
    מהדלת השנייה. זורקת DataUnavailable."""
    from datetime import date, timedelta
    client = get_client()
    if not client:
        raise DataUnavailable("series_pivot: no client")
    today = today or clock.today()
    month_start = today.replace(day=1)
    try:
        tpl = _maybe_one(client.table("transactions").select("*")
                         .eq("id", template_id).eq("family_id", family_id).eq("is_recurring", True))
        if not tpl:
            return "none", None
        if date.fromisoformat(str(tpl["date"])[:10]) >= month_start:
            return "template", None
        rows = client.table("transactions").select("id, date") \
            .eq("family_id", family_id).eq("recurring_parent_id", template_id) \
            .gte("date", month_start.isoformat()).order("date", desc=True).limit(1).execute().data or []
    except Exception as e:
        raise DataUnavailable("series_pivot") from e
    if rows:
        return "instance", (rows[0]["id"], str(rows[0]["date"])[:10])
    skips = {str(d)[:10] for d in (tpl.get("recurring_skips") or [])}
    for d in _recurring_occurrences(tpl, today + timedelta(days=400)):
        if d > today and d.isoformat() not in skips:
            return "future", d.isoformat()
    return "none", None


def create_occurrence(template_id: str, family_id: str, on_date: str):
    """יוצרת מופע של תבנית בתאריך נתון — כמו שהמנוע היה יוצר אותו (אותם
    שדות כמו ב-‎materialize_recurring‎). בשביל עריכה "מעכשיו" כשהמופע של
    החודש עוד לא נוצר: הוא נוצר עכשיו, ואז הסדרה מתפצלת בו. כשיגיע התאריך
    המנוע יראה שהתקופה תפוסה ולא יכפיל. מחזירה (id, error)."""
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        t = _maybe_one(client.table("transactions").select("*")
                       .eq("id", template_id).eq("family_id", family_id).eq("is_recurring", True))
        if not t:
            return None, None
        row = client.table("transactions").insert({
            "amount":              t["amount"],
            "type":                t["type"],
            "date":                on_date,
            "description":         t.get("description") or "",
            "category_id":         t.get("category_id"),
            "project_id":          t.get("project_id"),
            "project_category_id": t.get("project_category_id"),
            "created_by":          t.get("created_by"),
            "user_id":             t.get("user_id"),
            "family_id":           family_id,
            "is_recurring":        False,
            "recurring_parent_id": t["id"],
            "recurring_frequency": t.get("recurring_frequency"),
            "workplace":           t.get("workplace"),
        }).execute().data
        return (row[0]["id"] if row else None), None
    except Exception as e:
        logger.exception("create_occurrence")
        return None, str(e)


def project_choice_needed(err) -> int:
    """כמה פרויקטים אישיים מחכים להחלטה, לפי השגיאה של הסרה/עזיבה; 0 אם
    זו שגיאה אחרת. המסד הוא היחיד שיכול לספור אותם — הם אישיים, ולכן
    מוסתרים מהמנהל שמסיר (מיגרציה ‎20260928120000‎)."""
    m = re.search(r"needs_project_choice:(\d+)", err or "")
    return int(m.group(1)) if m else 0


def remove_family_member(user_id: str, keep_transactions: bool = True, projects: str = "ask"):
    """מסירה בן משפחה. מנהל המשפחה בלבד. מחזירה (ok, error).

    הכללים נאכפים ב-DB ולא כאן: הפונקציה נגזרת מ-auth.uid(), בודקת שהקורא
    הוא המנהל ושהיעד אכן במשפחה שלו, ומסרבת להסיר את המנהל עצמו — אחרת שני
    חברים היו יכולים להסיר זה את זה עד שלא נשאר אף אחד."""
    client = get_client()
    if not client:
        return False, "Database not configured"
    try:
        client.rpc("remove_family_member",
                   {"p_user_id": user_id, "p_keep_transactions": keep_transactions,
                    "p_projects": projects}).execute()
        return True, None
    except Exception as e:
        logger.exception("remove_family_member")
        return False, str(e)


def leave_family(keep_transactions: bool = True, projects: str = "ask"):
    """עוזבת את המשפחה הנוכחית ופותחת משפחה חדשה וריקה.
    מחזירה (new_family_id, error).

    ‎projects‎ (גם ב-‎remove_family_member‎): מה עושים עם הפרויקטים האישיים
    של מי שיוצא — ‎share‎ / ‎delete‎ / ‎ask‎. ב-‎ask‎, כשיש כאלה, השגיאה היא
    ‎needs_project_choice:N‎ (ראו ‎project_choice_needed‎) והמסך שואל."""
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        result = client.rpc("leave_family",
                            {"p_keep_transactions": keep_transactions,
                             "p_projects": projects}).execute()
        return (result.data or None), None
    except Exception as e:
        logger.exception("leave_family")
        return None, str(e)


def is_family_manager() -> bool:
    """האם המשתמש המחובר הוא מנהל המשפחה שלו.

    דרך RPC ולא דרך קריאה ל-families: הפונקציה נגזרת מ-‎auth.uid()‎ ולא
    מפרמטר, כך שאי אפשר לשאול אותה על מישהו אחר. היא מחזירה בוליאני
    בלבד — מזהה המנהל לא נחשף למי שלא אמור לראותו.

    זורקת ‎DataUnavailable‎ בכישלון: "לא ידוע" חייב להיקרא כ"לא מנהל"
    אצל הקורא, והכיוון הזה חייב להיות מפורש ולא תוצאה של ‎False‎ שקט."""
    client = get_client()
    if not client:
        raise DataUnavailable("is_family_manager: no client")
    try:
        return bool(client.rpc("is_family_manager", {}).execute().data)
    except Exception as e:
        raise DataUnavailable("is_family_manager") from e


def renew_expired_invite_code():
    """מחדשת את קוד ההזמנה **רק אם הוא חסר או פג**, ומחזירה את הקוד שבתוקף.
    כל בן משפחה רשאי — היא לא יכולה לבטל קוד תקף (מיגרציה 20260929120000).
    מחזירה (code, error)."""
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        code = client.rpc("renew_expired_invite_code", {}).execute().data
        _invalidate_family_cache(get_my_family_id() or "")
        return (code or None), None
    except Exception as e:
        logger.exception("renew_expired_invite_code")
        return None, str(e)


def rotate_invite_code():
    """מחליפה את קוד ההזמנה גם כשהוא בתוקף — כלומר מבטלת הזמנות שנשלחו.
    מנהל המשפחה בלבד (נאכף במסד). מחזירה (new_code, error)."""
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        result = client.rpc("rotate_invite_code", {}).execute()
        _invalidate_family_cache(get_my_family_id() or "")
        return (result.data or None), None
    except Exception as e:
        logger.exception("rotate_invite_code")
        return None, str(e)


def get_my_family_id():
    """מזהה המשפחה של המשתמש המחובר, לפי ה-DB ולא לפי ה-session."""
    client = get_client()
    if not client:
        return None
    try:
        return client.rpc("get_my_family_id", {}).execute().data
    except Exception:
        logger.exception("get_my_family_id")
        return None


def stop_recurring(transaction_id: str, family_id: str):
    """עוצרת סדרה קבועה בלי למחוק כסף. מחזירה (ok, error).

    "הסר את העסקה הקבועה" בהגדרות מבטיח למשתמש: "מופעים חדשים יפסיקו
    להיווצר. מופעים שכבר נוצרו יישארו." בפועל זה הריץ מחיקה מלאה של
    שורת התבנית — ושורת התבנית היא עסקה אמיתית לכל דבר, המופע הראשון
    בסדרה, שנספרת בסיכום החודשי. כלומר שכר הדירה של החודש הראשון נעלם
    מההיסטוריה בשקט, בניגוד גמור למה שנכתב בדיאלוג.

    ובנוסף, המחיקה ניתקה את כל המופעים מהתבנית (‎on delete set null‎),
    כך שמנגנון הדדופ הפסיק לראות אותם — ומי שיצר את אותה עסקה קבועה
    מחדש קיבל את כל החודשים בשנית.

    כיבוי הדגל פותר את שניהם: השורה נשארת כעסקה רגילה, הקישור שורד,
    ולא נוצרים מופעים חדשים."""
    client = get_client()
    if not client:
        return False, "Database not configured"
    try:
        result = client.table("transactions").update({
            "is_recurring":         False,
            "recurring_frequency":  None,
            "recurring_end_date":   None,
        }).eq("id", transaction_id).eq("family_id", family_id).execute()
        if not result.data:
            return False, "not found"
        return True, None
    except Exception as e:
        logger.exception("stop_recurring")
        return False, str(e)


def _maybe_one(query):
    """שורה אחת או ‎None‎.

    ב-postgrest-py שלנו (0.16) ‎.maybe_single().execute()‎ מחזיר ‎None‎ —
    לא תשובה עם ‎.data = None‎ — כשאין שורה. ‎.execute().data‎ זרק אז
    ‎AttributeError‎, והוא הפך ל-‎DataUnavailable‎: מחיקה של עסקה שבן משפחה
    אחר מחק רגע קודם ענתה "לא הצלחנו לבדוק אם זו עסקה קבועה — נסו שוב",
    ושום ניסיון נוסף לא עזר."""
    result = query.maybe_single().execute()
    return result.data if result is not None else None


def recurring_occurrence(transaction_id: str, family_id: str):
    """מה העסקה הזאת בתוך סדרה קבועה. מחזירה ‎(info, ok)‎ או זורקת.

    ‎info‎ הוא ‎None‎ לעסקה רגילה, או ‎{"template_id", "date", "later"}‎ —
    מזהה התבנית, תאריך המופע הזה, וכמה מופעים יש ממנו והלאה (כולל).

    אין כאן הבחנה בין "תבנית" ל"מופע", וזו ההחלטה: ההבחנה הזאת היא
    פנימית לגמרי — שורת התבנית היא עסקה רגילה לכל דבר שבמקרה גם
    מגדירה את הסדרה. למשתמש שמוחק את שכר הדירה של מרץ לא אמור להיות
    אכפת אם מרץ הוא במקרה החודש שבו הסדרה נפתחה."""
    client = get_client()
    if not client:
        raise DataUnavailable("recurring_occurrence: no client")
    try:
        row = _maybe_one(client.table("transactions") \
            .select("id, date, is_recurring, recurring_parent_id") \
            .eq("id", transaction_id).eq("family_id", family_id))
        if not row:
            return None, True
        template_id = row["id"] if row.get("is_recurring") else row.get("recurring_parent_id")
        if not template_id:
            return None, True

        # כמה מופעים מהתאריך הזה והלאה — כולל שורת התבנית עצמה, שהיא
        # המופע הראשון ולא נושאת recurring_parent_id
        later = client.table("transactions").select("id", count="exact") \
            .eq("family_id", family_id) \
            .eq("recurring_parent_id", template_id) \
            .gte("date", str(row["date"])).execute().count or 0
        template = client.table("transactions").select("id", count="exact") \
            .eq("family_id", family_id).eq("id", template_id) \
            .gte("date", str(row["date"])).execute().count or 0
        return {"template_id": template_id, "date": str(row["date"]),
                "later": later + template}, True
    except Exception as e:
        raise DataUnavailable("recurring_occurrence") from e


def transaction_type(transaction_id: str, family_id: str):
    """סוג העסקה (‎expense‎/‎income‎/‎savings‎), או ‎None‎ אם לא נמצאה.

    נדרש כדי לאמת שקטגוריה מתאימה לסוג — הסוג עצמו לא נשלח בגוף
    הבקשה במסלול הסנכרון, והוא לא ניתן לשינוי שם ממילא."""
    client = get_client()
    if not client:
        raise DataUnavailable("transaction_type: no client")
    try:
        row = _maybe_one(client.table("transactions").select("type") \
            .eq("id", transaction_id).eq("family_id", family_id))
        return (row or {}).get("type")
    except Exception as e:
        raise DataUnavailable("transaction_type") from e


def is_recurring_instance(transaction_id: str, family_id: str) -> bool:
    """האם העסקה היא מופע שנוצר מסדרה קבועה (ולא תבנית בפני עצמה).

    משמש רק לחסימה אחת: סימון "עסקה קבועה" על מופע קיים היה מייצר
    תבנית שנייה שרצה במקביל לראשונה, לתמיד. במחיקה, לעומת זאת, אין
    שום הבחנה בין תבנית למופע — ראו ‎recurring_occurrence‎."""
    client = get_client()
    if not client:
        raise DataUnavailable("is_recurring_instance: no client")
    try:
        row = _maybe_one(client.table("transactions").select("recurring_parent_id") \
            .eq("id", transaction_id).eq("family_id", family_id))
        return bool(row and row.get("recurring_parent_id"))
    except Exception as e:
        raise DataUnavailable("is_recurring_instance") from e


def delete_one_occurrence(transaction_id: str, template_id: str,
                          occurrence_date: str, family_id: str):
    """מוחקת מופע בודד מסדרה קבועה. מחזירה ‎(ok, error)‎.

    הכול קורה בפונקציית מסד אחת, ולא בשלוש קריאות מכאן, משתי סיבות:

    **הסדרה שרדה בקושי.** כשהשורה הנמחקת היא התבנית עצמה,
    ‎recurring_parent_id‎ (שהוא ‎on delete set null‎) ייתם בבת אחת את כל
    המופעים שנוצרו ממנה. הפונקציה מעבירה את תפקיד התבנית למופע הבא
    במקום להרוג את הסדרה.

    **‎recurring_skips‎ היה read-modify-write.** שני בני משפחה שמחקו שני
    מופעים באותה שנייה איבדו דילוג אחד, והעסקה חזרה למחרת — בדיוק הבאג
    שהעמודה נוספה כדי למנוע. במסד זה עדכון אטומי אחד.

    ‎template_id‎ ו-‎occurrence_date‎ נשארים בחתימה לטובת הקוראים, אבל
    הפונקציה נגזרת מהשורה עצמה — ולכן אין דרך שהיא תפעל על שורה אחת
    ותרשום דילוג על אחרת.
    """
    client = get_client()
    if not client:
        return False, "Database not configured"
    try:
        result = client.rpc("delete_recurring_occurrence", {
            "p_tx_id":     transaction_id,
            "p_family_id": family_id,
        }).execute()
        deleted = int(result.data or 0)
        return (deleted > 0), (None if deleted else "not found")
    except Exception as e:
        logger.exception("delete_one_occurrence")
        return False, str(e)

def delete_occurrences_from(template_id: str, occurrence_date: str, family_id: str):
    """מוחקת את המופע הזה וכל המאוחרים ממנו, ועוצרת את הסדרה שם.
    מחזירה (deleted, error).

    ‎recurring_end_date‎ נקבע ליום שלפני, ולא מכבים את הדגל: כך ההיסטוריה
    שלפני התאריך נשארת סדרה מזוהה — עם הקישורים שלה ועם ההגנה מפני
    כפילות — במקום להפוך לאוסף שורות יתומות."""
    from datetime import date, timedelta

    client = get_client()
    if not client:
        return 0, "Database not configured"
    try:
        removed = client.table("transactions").delete() \
            .eq("family_id", family_id) \
            .eq("recurring_parent_id", template_id) \
            .gte("date", occurrence_date).execute().data or []

        cutoff = date.fromisoformat(occurrence_date) - timedelta(days=1)
        template = _maybe_one(client.table("transactions").select("id, date") \
            .eq("id", template_id).eq("family_id", family_id))
        if not template:
            return len(removed), None

        if str(template["date"]) >= occurrence_date:
            # הסדרה נמחקת מתחילתה — אין מה להשאיר
            removed += client.table("transactions").delete() \
                .eq("id", template_id).eq("family_id", family_id) \
                .execute().data or []
        else:
            client.table("transactions") \
                .update({"recurring_end_date": cutoff.isoformat()}) \
                .eq("id", template_id).eq("family_id", family_id).execute()
        return len(removed), None
    except Exception as e:
        logger.exception("delete_occurrences_from")
        return 0, str(e)


def delete_transaction(transaction_id: str, family_id: str):
    """מחזירה ‎(ok, err)‎: ‎(True, None)‎, או ‎(False, "not found")‎ כשהעסקה כבר
    לא קיימת — בן משפחה אחר מחק אותה רגע קודם — או ‎(False, "error")‎.
    ההבחנה קובעת מה המשתמש רואה: "כבר נמחקה" והשורה יורדת מהמסך, מול
    "המחיקה נכשלה" והשורה נשארת."""
    client = get_client()
    if not client:
        return False, "error"
    try:
        # ‎.data‎ מחזיר את השורות שנמחקו בפועל (‎returning=representation‎
        # הוא ברירת המחדל). בלי הבדיקה הזאת הפונקציה החזירה ‎True‎ גם
        # כששום שורה לא נגעה — עסקה שבן משפחה אחר מחק לפני שנייה, או
        # מזהה של משפחה אחרת — והמשתמש קיבל "נמחק".
        result = client.table("transactions") \
            .delete() \
            .eq("id", transaction_id) \
            .eq("family_id", family_id) \
            .execute()
        return (True, None) if result.data else (False, "not found")
    except Exception:
        # המשתמש כן רואה "מחיקה נכשלה", אז זה לא כשל שקט — אבל בלי
        # הרישום אי אפשר לענות על "למה".
        logger.exception("delete_transaction")
        return False, "error"


# ─── Categories ───────────────────────────────────────────────────────────────

def family_needs_onboarding(family_id: str) -> bool:
    """A family with zero categories hasn't finished onboarding yet
    (brand-new families start with none — see /onboarding)."""
    client = get_client()
    if not client or not family_id:
        return False
    try:
        result = client.table("categories").select("id", count="exact") \
            .eq("family_id", family_id).limit(1).execute()
        return (result.count or 0) == 0
    except Exception as e:
        raise DataUnavailable("family_needs_onboarding") from e


def family_has_no_transactions(family_id: str) -> bool:
    """True אם המשפחה מעולם לא הוסיפה עסקה — משמש להצגת הודעת פתיחה ידידותית
    בדשבורד במקום קיר של ₪0, ולא נבדק לפי החודש הנוכחי (משפחה ותיקה שעוד
    לא הזינה כלום החודש לא אמורה להיחשב 'חדשה')."""
    client = get_client()
    if not client or not family_id:
        return False
    try:
        result = client.table("transactions").select("id", count="exact") \
            .eq("family_id", family_id).limit(1).execute()
        return (result.count or 0) == 0
    except Exception as e:
        raise DataUnavailable("family_has_no_transactions") from e


_MAX_CATEGORIES_PER_FAMILY = 200


def bulk_add_categories(family_id: str, categories: list) -> tuple:
    """Inserts multiple categories at once for a family's onboarding.
    `categories` is a list of {name, icon, type} dicts. Returns (count, error).
    sort_order נקבע לפי הסדר ברשימת הקלט (בתוך כל סוג בנפרד) — כך שהסדר
    ההתחלתי תואם למה שהוגדר ב-_DEFAULT_CATEGORIES."""
    client = get_client()
    if not client:
        return 0, "Database not configured"
    # תקרה. הרשימה הגיעה מגוף הבקשה בלי שום גבול, ועם תקרת 8MB זה
    # ~100,000 שורות ב-‎insert‎ אחד — ובנוסף ‎_validated_category‎ סורק את
    # הרשימה הזאת ליניארית בכל כתיבת עסקה, אז כל עסקה עתידית משלמת עליה.
    #
    # ‎_DEFAULT_CATEGORIES‎ הוא כמה עשרות; 200 הוא הרבה מעל כל אשף אמיתי.
    if len(categories or []) > _MAX_CATEGORIES_PER_FAMILY:
        return 0, "יותר מדי קטגוריות בבת אחת"

    counters = {"income": 0, "expense": 0, "savings": 0}
    rows = []
    for c in categories:
        if not c.get("name") or c.get("type") not in counters:
            continue
        counters[c["type"]] += 1
        rows.append({
            "name": c["name"], "icon": c.get("icon", "📦"), "type": c["type"],
            "family_id": family_id, "is_custom": True, "sort_order": counters[c["type"]],
        })
    if not rows:
        return 0, "No valid categories provided"
    try:
        result = client.table("categories").insert(rows).execute()
        return len(result.data or []), None
    except Exception as e:
        return 0, str(e)


def _fetch_categories(family_id: str = None) -> list:
    client = get_client()
    if not client:
        return []
    try:
        query = client.table("categories").select("*")
        if family_id:
            query = query.or_(f"family_id.is.null,family_id.eq.{family_id}")
        else:
            query = query.is_("family_id", "null")
        return query.order("sort_order", nullsfirst=False).order("name").execute().data
    except Exception as e:
        # רשימה ריקה נקראת בדשבורד כ"משפחה חדשה" ומפנה לאשף ההרשמה
        raise DataUnavailable("categories") from e


def get_categories(family_id: str = None) -> list:
    """ממוטב-לבקשה: נקרא 3-4 פעמים בעמודים כבדים (פירוט לפי קטגוריה ×3),
    אז השליפה נשמרת ב-flask.g לאורך הבקשה."""
    return _request_cache(f"categories:{family_id}", lambda: _fetch_categories(family_id))


def update_category(cat_id: str, family_id: str, name: str, icon: str):
    """Updates a family category's name and icon."""
    client = get_client()
    if not client:
        return False
    try:
        result = client.table("categories") \
            .update({"name": name, "icon": icon}) \
            .eq("id", cat_id) \
            .eq("family_id", family_id) \
            .execute()
        # ‎.data‎ מחזיר את השורות שנגעו בפועל. בלי הבדיקה הזאת "נשמר"
        # נאמר גם כששום שורה לא התאימה — למשל כשבן משפחה אחר מחק את
        # הפריט שנייה קודם, או כשהמזהה שייך למשפחה אחרת.
        return bool(result.data)
    except Exception:
        logger.exception("update_category")
        return False


def add_custom_category(family_id: str, name: str, icon: str, type_: str):
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        existing = client.table("categories").select("sort_order") \
            .eq("family_id", family_id).eq("type", type_).execute().data or []
        next_order = max([c.get("sort_order") or 0 for c in existing], default=0) + 1
        result = client.table("categories").insert({
            "name": name, "icon": icon, "type": type_,
            "family_id": family_id, "is_custom": True, "sort_order": next_order,
        }).execute()
        return result.data[0] if result.data else None, None
    except Exception as e:
        return None, str(e)


def reorder_categories(family_id: str, type_: str, ordered_ids: list) -> bool:
    """מעדכן את sort_order של קטגוריות מסוג נתון לפי הסדר שהתקבל."""
    client = get_client()
    if not client:
        return False
    try:
        for i, cat_id in enumerate(ordered_ids, start=1):
            client.table("categories").update({"sort_order": i}) \
                .eq("id", cat_id).eq("family_id", family_id).eq("type", type_).execute()
        return True
    except Exception:
        logger.exception("reorder_categories")
        return False


# ─── Projects (תקציבי פרויקטים — משותפים או אישיים לבן משפחה אחד) ─────────────

def get_projects(family_id: str, viewer_user_id: str, archived=False) -> list:
    """פרויקטים גלויים לצופה הנוכחי: כל הפרויקטים המשותפים + הפרויקטים
    האישיים ששייכים לו עצמו. פרויקט אישי של בן משפחה אחר לא נכלל כאן בכלל —
    זו הפרטיות המבוקשת (לא רק מוסתר בתצוגה, אלא לא נשלף כלל).

    ‎archived‎: ‎False‎ — הפעילים (ברירת המחדל, כל רשימה רגילה); ‎True‎ —
    "פרויקטים שהסתיימו"; ‎None‎ — כולם, מסומנים (טופס העסקה, לעסקה ישנה)."""
    client = get_client()
    if not client or not family_id:
        return []
    try:
        query = client.table("projects").select("*").eq("family_id", family_id)
        if archived is not None:
            query = query.eq("archived", bool(archived))
        projects = query.order("created_at", desc=True).execute().data
        visible = [p for p in projects if not p.get("owner_id") or p["owner_id"] == viewer_user_id]

        totals = _project_totals(family_id)
        out = []
        for p in visible:
            t = totals.get(p["id"], {"expense": 0.0, "income": 0.0, "savings": 0.0})
            # "הסכום הנוכחי" המוצג ברשימה: נטו — הכנסות+חיסכון פחות הוצאות
            net = t["income"] + t["savings"] - t["expense"]
            budget = p.get("budget_target")
            out.append({
                "id": p["id"], "name": p["name"],
                "description": p.get("description"),
                "icon": p.get("icon"),
                "is_personal": bool(p.get("owner_id")),
                "owner_id": p.get("owner_id"),
                "budget_target": float(budget) if budget is not None else None,
                "amount": round(net, 2),
                "track_expense": p.get("track_expense", True),
                "track_income": p.get("track_income", False),
                "track_savings": p.get("track_savings", False),
                "archived": bool(p.get("archived")),
            })
        return out
    except Exception as e:
        logger.exception("get_projects")
        raise DataUnavailable("get_projects") from e


def _project_totals(family_id: str) -> dict:
    """סכום כל הזמן לכל פרויקט, מפורק לפי סוג עסקה (expense/income/savings).

    מחושב במסד (RPC ‎project_totals‎) ולא בפייתון. הגרסה הקודמת משכה את
    *כל* עסקאות הפרויקטים של המשפחה, מאז ומתמיד, בכל טעינה של עמוד
    ההגדרות והפרויקטים — וחיברה אותן כאן. אצל משפחה עם טיול אחד זה כבר
    56 שורות שנמשכות כדי לקבל מספר אחד, והמספר גדל לנצח.

    ה-RPC הוא ‎security invoker‎, כך ש-RLS ממשיכה לחול ולא נפתחה פה
    דלת לראות פרויקטים של משפחה אחרת."""
    client = get_client()
    if not client:
        return {}
    rows = client.rpc("project_totals", {"p_family_id": family_id}).execute().data or []
    return {
        r["project_id"]: {
            "expense": float(r["expense"] or 0),
            "income":  float(r["income"] or 0),
            "savings": float(r["savings"] or 0),
        }
        for r in rows
    }


def add_project(family_id: str, name: str, created_by: str, budget_target: float = None,
                owner_id: str = None, description: str = None, icon: str = None,
                track_expense: bool = True, track_income: bool = False, track_savings: bool = False):
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        result = client.table("projects").insert({
            "family_id": family_id, "name": name, "budget_target": budget_target,
            "owner_id": owner_id, "created_by": created_by, "description": description,
            "icon": icon, "track_expense": track_expense,
            "track_income": track_income, "track_savings": track_savings,
        }).execute()
        project = result.data[0] if result.data else None
        if project:
            types = [t for t, on in (("expense", track_expense), ("income", track_income),
                                     ("savings", track_savings)) if on]
            _seed_project_categories(project["id"], family_id, types)
        return project, None
    except Exception as e:
        return None, str(e)


def set_project_archived(project_id: str, family_id: str, archived: bool) -> bool:
    """"הפרויקט הסתיים" / "פתיחה מחדש" (מתן, 30.9). העסקאות לא נוגעות —
    רק הדגל, שמוציא את הפרויקט מהרשימות ומטופס ההוספה. ‎False‎ כששום שורה
    לא נגעה (נמחק בינתיים, או לא של המשפחה)."""
    client = get_client()
    if not client:
        return False
    try:
        res = client.table("projects").update({"archived": bool(archived)}) \
            .eq("id", project_id).eq("family_id", family_id).execute()
        return bool(res.data)
    except Exception:
        logger.exception("set_project_archived")
        return False


def update_project(project_id: str, family_id: str, name: str, budget_target: float = None,
                   description: str = None, icon: str = None, track_expense: bool = True,
                   track_income: bool = False, track_savings: bool = False):
    """מעדכן שם/יעד/סוגי מעקב בלבד. שינוי בעלות (אישי/משותף) נעשה רק דרך
    share_project/unshare_project הייעודיות — לא כאן."""
    client = get_client()
    if not client:
        return False
    try:
        rows = client.table("projects") \
            .select("track_expense, track_income, track_savings") \
            .eq("id", project_id).eq("family_id", family_id).limit(1).execute().data
        if not rows:
            return None                 # נמחק בינתיים — המסלול אומר את זה (404)
        existing = rows[0]
        # סוגים שהופעלו כרגע לראשונה — נזרע להם קטגוריות התחלתיות
        newly_enabled = [
            t for t, before, after in (
                ("expense", existing.get("track_expense"), track_expense),
                ("income", existing.get("track_income"), track_income),
                ("savings", existing.get("track_savings"), track_savings),
            ) if after and not before
        ]

        result = client.table("projects").update({
            "name": name, "budget_target": budget_target, "description": description,
            "icon": icon, "track_expense": track_expense, "track_income": track_income,
            "track_savings": track_savings,
        }).eq("id", project_id).eq("family_id", family_id).execute()
        # ראו update_category
        if not result.data:
            return False

        if newly_enabled:
            _seed_project_categories(project_id, family_id, newly_enabled)
        return True
    except Exception:
        logger.exception("update_project")
        return False


def share_project(project_id: str, family_id: str, user_id: str):
    """הופך פרויקט אישי למשותף: נפתח לכל בני המשפחה, וכל העסקאות שכבר
    שויכו אליו הופכות לשיוך משותף (user_id=NULL) — תואם לבקשת מתן שהמעבר
    למשותף גורר גם את ההוצאות/הכנסות עצמן. רק הבעלים הנוכחי רשאי לבצע זאת."""
    client = get_client()
    if not client:
        return False, "Database not configured"
    try:
        # לא ‎.single()‎: על פרויקט שנמחק רגע קודם הוא זרק, והמשתמש קיבל שגיאה
        # כללית במקום "נמחק בינתיים" (סקירה של 1.10)
        rows = client.table("projects").select("owner_id") \
            .eq("id", project_id).eq("family_id", family_id).limit(1).execute().data
        proj = rows[0] if rows else None
        if not proj:
            return False, "הפרויקט לא נמצא — ייתכן שנמחק בינתיים"
        if proj.get("owner_id") != user_id:
            return False, "רק הבעלים של הפרויקט יכול להפוך אותו למשותף"
        client.table("projects").update({"owner_id": None}) \
            .eq("id", project_id).eq("family_id", family_id).execute()
        client.table("transactions").update({"user_id": None}) \
            .eq("project_id", project_id).eq("family_id", family_id).execute()
        return True, None
    except Exception as e:
        return False, str(e)


def unshare_project(project_id: str, family_id: str, user_id: str):
    """מחזיר פרויקט משותף להיות אישי — רק מי שיצר את הפרויקט במקור (created_by)
    רשאי לבצע זאת, גם אם הפרויקט משותף כרגע ולכולם יש אליו גישה."""
    client = get_client()
    if not client:
        return False, "Database not configured"
    try:
        rows = client.table("projects").select("owner_id, created_by") \
            .eq("id", project_id).eq("family_id", family_id).limit(1).execute().data
        proj = rows[0] if rows else None
        if not proj:
            return False, "הפרויקט לא נמצא — ייתכן שנמחק בינתיים"
        if proj.get("owner_id"):
            return False, "הפרויקט כבר אישי"
        if proj.get("created_by") != user_id:
            return False, "רק מי שיצר את הפרויקט יכול להחזיר אותו להיות אישי"
        client.table("projects").update({"owner_id": user_id}) \
            .eq("id", project_id).eq("family_id", family_id).execute()
        return True, None
    except Exception as e:
        return False, str(e)


def delete_project(project_id: str, family_id: str):
    """מוחק את הפרויקט, את קטגוריותיו (ON DELETE CASCADE) — ואת העסקאות שבו.

    הייתה בחירה "להשאיר את העסקאות", והמסך הבטיח שהן "יחזרו לקטגוריה
    הרגילה שלהן". לעסקת פרויקט אין קטגוריה רגילה: היא נחתה בהוצאות הבית
    כ"ללא קטגוריה" (ON DELETE SET NULL), והחודשים שבהם נרשמה התייקרו
    בדיעבד — שיפוץ של ₪40,000 על שלושה חודשים. מתן החליט (28.9.2026):
    מחיקת פרויקט מוחקת את העסקאות שבו. כסף של פרויקט ממילא לא נספר
    בהוצאות הבית, אז אף סכום של הבית לא זז. כל עסקה נמחקת עוברת דרך
    הטריגר לארכיון הפנימי."""
    client = get_client()
    if not client:
        return False, 0
    try:
        # קודם לוודא שהפרויקט עוד קיים: אחרת "לא נמצא" היה חוזר אחרי שהעסקאות
        # כבר נמחקו — בדיוק כשבן משפחה אחר מחק אותו שנייה קודם.
        exists = client.table("projects").select("id") \
            .eq("id", project_id).eq("family_id", family_id).limit(1).execute().data
        if not exists:
            return False, 0
        gone = client.table("transactions").delete() \
            .eq("project_id", project_id).eq("family_id", family_id).execute()
        wiped = len(gone.data or [])
        result = client.table("projects").delete() \
            .eq("id", project_id).eq("family_id", family_id).execute()
        # ‎(ok, wiped)‎ ולא ‎True‎: זו הפעולה ההרסנית ביותר שכל חבר יכול
        # לעשות בלי סיסמה ובלי הרשאת מנהל, והמשתמש צריך לראות כמה עסקאות
        # באמת נעלמו — בדיוק כמו באיפוס העסקאות.
        return bool(result.data), wiped
    except Exception:
        logger.exception("delete_project")
        return False, 0


def get_project_for_transaction(project_id: str, family_id: str):
    """שדות מינימליים הנחוצים לאימות ואכיפה בהוספת/עדכון עסקה משויכת
    לפרויקט: owner_id (לאכיפת שיוך אוטומטי) ודגלי המעקב (לוודא שהסוג נתמך)."""
    client = get_client()
    if not client:
        return None
    try:
        return client.table("projects") \
            .select("owner_id, track_expense, track_income, track_savings") \
            .eq("id", project_id).eq("family_id", family_id).single().execute().data
    except Exception:
        # שני הקוראים מפרשים None כ"הפרויקט לא נמצא" ומסרבים — הכיוון
        # הבטוח. אבל למשתמש זה נראה כאילו פרויקט קיים נעלם, וזה בדיוק
        # הדיווח שאי אפשר לחקור בלי traceback.
        logger.exception("get_project_for_transaction")
        return None


def get_project_detail(project_id: str, family_id: str, viewer_user_id: str) -> dict:
    """פרטי פרויקט + כל העסקאות שלו, מכל החודשים ביחד. אם זה פרויקט אישי
    ששייך לבן משפחה אחר — מחזיר None (חסימת גישה מלאה, לא רק הסתרה)."""
    client = get_client()
    if not client or not family_id:
        return None
    # מזהה משובש (קישור שנחתך) — PostgREST היה דוחה אותו בשגיאה, והיא 503
    if not _UUID_RE.match(str(project_id)):
        return None
    try:
        # לא ‎.single()‎: על אפס שורות הוא זורק, וזה הפך פרויקט שנמחק לדף
        # תקלה ("נסו לרענן") במקום ל"לא קיים"
        found = client.table("projects").select("*") \
            .eq("id", project_id).eq("family_id", family_id).limit(1).execute().data
        if not found:
            return None
        proj = found[0]
        if proj.get("owner_id") and proj["owner_id"] != viewer_user_id:
            return None

        result = client.table("transactions") \
            .select("*, categories(name, icon), project_categories(name, icon), profiles(name, workplace)") \
            .eq("family_id", family_id).eq("project_id", project_id) \
            .order("date", desc=True).execute()
        transactions = _format_transactions(result.data)

        totals = {"expense": 0.0, "income": 0.0, "savings": 0.0}
        # חלוקה לפי קטגוריה לכל סוג — מחושב מהעסקאות שכבר נשלפו (בלי שליפה נוספת)
        grouped = {"expense": {}, "income": {}, "savings": {}}
        for t in transactions:
            typ = t["type"]
            if typ not in totals:
                continue
            totals[typ] += t["amount"]
            key = t.get("category_name") or "אחר"
            entry = grouped[typ].setdefault(
                key, {"name": key, "icon": t.get("category_icon") or "📦", "total": 0.0})
            entry["total"] += t["amount"]

        breakdown = {}
        for typ, cats in grouped.items():
            items = [c for c in cats.values() if c["total"] > 0]
            tot = sum(c["total"] for c in items) or 1
            for c in items:
                c["pct"] = round(c["total"] / tot * 100)
                c["total"] = round(c["total"], 2)
            items.sort(key=lambda c: c["total"], reverse=True)
            breakdown[typ] = items

        budget = proj.get("budget_target")
        spent = totals["expense"]
        return {
            "id": proj["id"], "name": proj["name"],
            "description": proj.get("description"),
            "icon": proj.get("icon"),
            "is_personal": bool(proj.get("owner_id")),
            "owner_id": proj.get("owner_id"),
            "created_by": proj.get("created_by"),
            "track_expense": proj["track_expense"], "track_income": proj["track_income"],
            "track_savings": proj["track_savings"],
            "archived": bool(proj.get("archived")),
            "budget_target": float(budget) if budget is not None else None,
            "spent": round(spent, 2),
            "income": round(totals["income"], 2),
            "savings": round(totals["savings"], 2),
            "remaining": round(float(budget) - spent, 2) if budget is not None else None,
            "breakdown": breakdown,
            "transactions": transactions,
        }
    except Exception as e:
        logger.exception("get_project_detail")
        raise DataUnavailable("get_project_detail") from e


# ─── Project categories (ייעודיות לכל פרויקט, נפרדות מקטגוריות המשפחה) ────────

def _seed_project_categories(project_id: str, family_id: str, types: list):
    """זריעת קטגוריות התחלתיות לפרויקט — עותק מקטגוריות המשפחה הרגילות
    מאותם סוגים, כברירת מחדל שניתן לערוך/למחוק/להוסיף עליה בלי להשפיע
    על קטגוריות המשפחה המקוריות."""
    if not types:
        return
    client = get_client()
    if not client:
        return
    try:
        family_cats = [c for c in get_categories(family_id) if c.get("type") in types]
        if not family_cats:
            return
        rows = [{
            "project_id": project_id, "family_id": family_id,
            "name": c["name"], "icon": c.get("icon", "📦"), "type": c["type"],
        } for c in family_cats]
        client.table("project_categories").insert(rows).execute()
    except Exception:
        logger.exception("_seed_project_categories")


def get_project_categories(project_id: str, family_id: str, type_: str = None) -> list:
    client = get_client()
    if not client:
        return []
    try:
        query = client.table("project_categories").select("*") \
            .eq("project_id", project_id).eq("family_id", family_id)
        if type_:
            query = query.eq("type", type_)
        return query.order("name").execute().data
    except Exception as e:
        logger.exception("get_project_categories")
        raise DataUnavailable("get_project_categories") from e


def add_project_category(project_id: str, family_id: str, name: str, icon: str, type_: str):
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        result = client.table("project_categories").insert({
            "project_id": project_id, "family_id": family_id,
            "name": name, "icon": icon, "type": type_,
        }).execute()
        return (result.data[0] if result.data else None), None
    except Exception as e:
        return None, str(e)


# ─── מחיקת קטגוריה: אין עסקה שנשארת בלי קטגוריה ─────────────────────────────
#
# מחיקה פשוטה השאירה את העסקאות של הקטגוריה "ללא קטגוריה" (ה-FK הוא ‎ON
# DELETE SET NULL‎). עכשיו הן מועברות לקטגוריה אחרת **לפני** המחיקה, ואילוץ
# ‎transactions_category_required‎ במסד תופס מירוץ: עסקה שנוספה לקטגוריה
# בין ההעברה למחיקה מכשילה את המחיקה, במקום להישאר יתומה.

# (טבלת הקטגוריות, העמודה בעסקה שמצביעה עליה)
_CATEGORY_KINDS = {
    "family":  ("categories", "category_id"),
    "project": ("project_categories", "project_category_id"),
}


def category_deletion_plan(kind: str, cat_id: str, family_id: str, project_id: str = None):
    """מה יקרה אם הקטגוריה תימחק: ‎{"category", "count", "alternatives"}‎,
    או ‎None‎ אם היא לא קיימת (או של משפחה/פרויקט אחרים).

    ‎alternatives‎ — הקטגוריות מאותו סוג, באותו מקום, שאפשר להעביר אליהן."""
    table, column = _CATEGORY_KINDS[kind]
    client = get_client()
    if not client:
        raise DataUnavailable("category_deletion_plan")
    try:
        def scoped(q):
            q = q.eq("family_id", family_id)
            return q.eq("project_id", project_id) if kind == "project" else q

        found = scoped(client.table(table).select("*").eq("id", cat_id)).execute().data
        if not found:
            return None
        category = found[0]
        siblings = scoped(client.table(table).select("id, name, icon, type")
                          .eq("type", category.get("type"))).execute().data
        used = client.table("transactions").select("id", count="exact") \
            .eq("family_id", family_id).eq(column, cat_id).limit(1).execute()
        return {
            "category": category,
            "count": used.count or 0,
            "alternatives": [{"id": c["id"], "name": c["name"], "icon": c.get("icon") or "📦"}
                             for c in siblings if c["id"] != cat_id],
        }
    except Exception as e:
        logger.exception("category_deletion_plan")
        raise DataUnavailable("category_deletion_plan") from e


def delete_category_moving(kind: str, cat_id: str, family_id: str,
                           move_to: str = None, project_id: str = None) -> bool:
    """מעביר את העסקאות של הקטגוריה ל-‎move_to‎ ואז מוחק אותה.
    הבדיקה שהיעד תקין היא של הקורא (‎category_deletion_plan‎)."""
    table, column = _CATEGORY_KINDS[kind]
    client = get_client()
    if not client:
        return False
    try:
        if move_to:
            client.table("transactions").update({column: move_to}) \
                .eq("family_id", family_id).eq(column, cat_id).execute()
        q = client.table(table).delete().eq("id", cat_id).eq("family_id", family_id)
        q = q.eq("project_id", project_id) if kind == "project" else q.eq("is_custom", True)
        return bool(q.execute().data)
    except Exception:
        logger.exception("delete_category_moving")
        return False

def update_project_category(cat_id: str, project_id: str, family_id: str, name: str, icon: str):
    client = get_client()
    if not client:
        return False
    try:
        result = client.table("project_categories").update({"name": name, "icon": icon}) \
            .eq("id", cat_id).eq("project_id", project_id).eq("family_id", family_id).execute()
        # ‎.data‎ מחזיר את השורות שנגעו בפועל. בלי הבדיקה הזאת "נשמר"
        # נאמר גם כששום שורה לא התאימה — למשל כשבן משפחה אחר מחק את
        # הפריט שנייה קודם, או כשהמזהה שייך למשפחה אחרת.
        return bool(result.data)
    except Exception:
        logger.exception("update_project_category")
        return False


def delete_project_category(cat_id: str, project_id: str, family_id: str) -> bool:
    client = get_client()
    if not client:
        return False
    try:
        result = client.table("project_categories").delete() \
            .eq("id", cat_id).eq("project_id", project_id).eq("family_id", family_id).execute()
        # ‎.data‎ מחזיר את השורות שנגעו בפועל. בלי הבדיקה הזאת "נשמר"
        # נאמר גם כששום שורה לא התאימה — למשל כשבן משפחה אחר מחק את
        # הפריט שנייה קודם, או כשהמזהה שייך למשפחה אחרת.
        return bool(result.data)
    except Exception:
        logger.exception("delete_project_category")
        return False


# ─── Analytics ───────────────────────────────────────────────────────────────

# ─── חודש אחד, שליפה אחת ──────────────────────────────────────────────────────
#
# עמוד החודש הריץ 12 פניות למסד, ושבע מהן קראו בדיוק את אותן שורות:
# הסיכום, שלושה פילוחים לקטגוריה ושניים לבן משפחה — כולם תת-קבוצות של
# העסקאות שכבר נשלפו לרשימת "כל העסקאות".
#
# הזמן (כ-180 מילישניות) הוא לא העיקר. העיקר הוא שכל אחת מהשבע גזרה
# לעצמה מחדש את אותם שני כללים — החרגת עסקאות פרויקט, והסתרת פרויקט
# אישי של בן משפחה אחר. הכלל השני נשכח פעם אחת כבר, וזה מתועד בהערה
# בקוד: עסקת פרויקט הופיעה בתוך קטגוריה חודשית בלי להיספר בסכום שלה.
#
# שליפה אחת עם גזירות בשמות ברורים הופכת את סוג הבאג הזה לבלתי אפשרי:
# אין מאיפה לשכוח את הכלל, כי הוא מיושם פעם אחת.

def fetch_month_page(family_id: str, year: int, month: int) -> dict:
    """כל מה שעמוד החודש צריך, בנסיעה אחת למסד.

    מחליפה חמש שליפות שרצו ברצף (הגדרות, חברים, קטגוריות, שורות החודש,
    ארכיון) — ראו ההערה ב-‎_run_queries‎ ב-app.py על למה הן רצות ברצף
    ולא במקביל, ואת המיגרציה ‎20260923120000_month_page_fn.sql‎ על למה
    התשובה היא פחות נסיעות ולא נסיעות מקבילות.

    העיבוד נשאר כאן ולא ירד ל-SQL בכוונה: ‎_merge_settings‎ וקיצור השמות
    הם אותו קוד שכל שאר האפליקציה עוברת דרכו, ושכפול שלהם במסד היה יוצר
    שני מקורות אמת שיכולים להיפרד בשקט.

    ‎null‎ מהפונקציה = המשפחה אינה של הקורא, או שהשליפה נכשלה. שניהם
    ‎DataUnavailable‎: אף אחד מהם אינו "משפחה בלי נתונים"."""
    client = get_client()
    if not client:
        raise DataUnavailable("fetch_month_page: no client")
    try:
        data = client.rpc("get_month_page", {
            "p_family_id": family_id,
            "p_year":      year,
            "p_month":     month,
        }).execute().data
    except Exception as e:
        raise DataUnavailable("fetch_month_page") from e

    if not data:
        raise DataUnavailable("fetch_month_page: empty")

    # זהה ל-‎_fetch_family_members‎: התבניות מציגות שם פרטי, והשם המלא
    # נשמר לצדו כי יש מקומות שמראים אותו במלואו.
    members = data.get("members") or []
    for m in members:
        m["full_name"] = m.get("name", "")
        m["name"] = first_name(m.get("name", ""))

    family = data.get("family") or {}
    return {
        "family":     family,
        "settings":   _merge_settings(DEFAULT_FAMILY_SETTINGS, family.get("settings") or {}),
        "members":    members,
        "categories": data.get("categories") or [],
        "rows":       data.get("rows") or [],
        "archive":    data.get("archive") or [],
    }


def fetch_month_rows(family_id: str, year: int, month: int) -> list:
    """כל שורות החודש, כולל עסקאות פרויקט, עם כל השיוכים.

    זו השליפה שממנה נגזר כל עמוד החודש. היא מחזירה גם עסקאות פרויקט —
    הגזירות למטה הן שמחליטות מי מתעלמת מהן ומי מציגה אותן."""
    client = get_client()
    if not client:
        raise DataUnavailable("fetch_month_rows: no client")
    try:
        return client.table("transactions") \
            .select("*, categories(name, icon), project_categories(name, icon), "
                    "profiles(name, workplace), projects(owner_id, name, icon)") \
            .eq("family_id", family_id) \
            .gte("date", f"{year}-{month:02d}-01") \
            .lt("date", _next_month(year, month)) \
            .order("date", desc=True) \
            .execute().data or []
    except Exception as e:
        raise DataUnavailable("fetch_month_rows") from e


def _household_rows(rows: list) -> list:
    """רק עסקאות שאינן משויכות לפרויקט.

    זה הכלל שכל הסיכומים החודשיים חולקים: פרויקט הוא הוצאה חד-פעמית
    שמעוותת את תמונת ה"חודש הרגיל", ולכן הוא מוצג בנפרד. מיושם כאן
    פעם אחת במקום בשבע שאילתות."""
    return [r for r in rows if not r.get("project_id")]


def summary_from_rows(rows: list) -> dict:
    """אותו סיכום כמו get_monthly_summary, מתוך שורות שכבר בידנו."""
    summary = _empty_summary()
    for row in _household_rows(rows):
        t = row["type"]
        if t in ("income", "expense", "savings"):
            summary[t] += float(row["amount"])
    for k in ("income", "expense", "savings"):
        summary[k] = round(summary[k], 2)
    summary["balance"]   = round(summary["income"] - summary["expense"], 2)
    summary["remaining"] = round(summary["balance"] - summary["savings"], 2)
    total = summary["income"] or 1
    summary["expense_pct"] = round(summary["expense"] / total * 100)
    return summary


# הדלי של עסקאות שאיבדו את הקטגוריה שלהן (הקטגוריה נמחקה — ‎ON DELETE
# SET NULL‎). בעבר הן התמזגו בשקט לתוך קטגוריית "אחר" של המשפחה, כי
# הקיבוץ היה לפי שם; עכשיו הן דלי נפרד ואפשר לראות שיש כסף שצריך שיוך.
_NO_CATEGORY = "ללא קטגוריה"


def category_breakdown_from_rows(rows: list, categories: list, type_: str) -> list:
    """סכום לכל קטגוריה מהסוג המבוקש.

    מקובץ לפי **מזהה** הקטגוריה, לא לפי שמה. שם הוא לא מפתח: אין במסד
    אילוץ ייחודיות על שמות קטגוריות, ושתי קטגוריות שונות באותו שם היו
    מתמזגות לשורה אחת שאיש לא ביקש. זה גם מה שהשתיק את תקציבי
    הקטגוריות — הם שמורים לפי מזהה, והשורות שיצאו מכאן לא נשאו אותו
    בכלל, אז ‎apply_budgets‎ חיפשה ולא מצאה **אף פעם**.

    כל קטגוריות הסוג מופיעות תמיד, גם בחודש שאין בו נתון עבורן — אחרת
    קטגוריה נעלמת מהעמוד בדיוק בחודש שבו לא הוצאת בה, וזה נראה כאילו
    נמחקה."""
    buckets = {c["id"]: {"category_id": c["id"], "name": c["name"],
                         "icon": c.get("icon", "📦"), "total": 0.0}
               for c in categories if c.get("type") == type_ and c.get("id")}

    for row in _household_rows(rows):
        if row["type"] != type_:
            continue
        cat = row.get("categories") or {}
        key = row.get("category_id")
        if key not in buckets:
            # קטגוריה שאינה ברשימה (נמחקה, או שייכת למשפחה אחרת דרך
            # נתון ישן) — לוקחים את השם המוטבע בשורה עצמה
            buckets[key] = {
                "category_id": key,
                "name": cat.get("name") or _NO_CATEGORY,
                "icon": cat.get("icon") or "📦",
                "total": 0.0,
            }
        buckets[key]["total"] += float(row["amount"])

    grand = sum(b["total"] for b in buckets.values()) or 1
    out = [{**b, "total": round(b["total"], 2),
            "pct": round(b["total"] / grand * 100)} for b in buckets.values()]
    out.sort(key=lambda x: (-x["total"], x["name"]))
    return out


# קטגוריית משכורת מזוהה לפי השם — כמו בחירת ברירת המחדל בטופס (‎transactions.js‎)
_SALARY_WORD = "משכורת"


def income_sources(transactions: list) -> list:
    """"הכנסות — מאיפה הגיעו" בעמוד החודש (מתן, 30.9): שורה לכל משכורת לפי מי
    שרשום עליה ("משכורת מתן", "משכורת אור"), ושורה אחת "הכנסות נוספות" לכל
    השאר. משכורות קודם, מהגדולה לקטנה; הנוספות אחרונות.

    מקבלת את עסקאות הבית של החודש (בלי פרויקטים — כמו ‎month_transactions‎).
    משכורת בלי בעלים (שיוך כבוי, או משותפת) היא פשוט "משכורת", בלי שם."""
    salaries, extra = {}, None
    for t in transactions:
        if t.get("type") != "income":
            continue
        if _SALARY_WORD in (t.get("category_name") or ""):
            key = t.get("user_id") or ""
            src = salaries.setdefault(key, {
                "kind": _SALARY_WORD, "who": t.get("user_name") if t.get("user_id") else "",
                "icon": t.get("category_icon") or "💼", "total": 0.0, "transactions": []})
        else:
            if extra is None:
                extra = {"kind": "הכנסות נוספות", "who": "", "icon": "➕",
                         "total": 0.0, "transactions": []}
            src = extra
        src["total"] += float(t["amount"])
        src["transactions"].append(t)
    out = sorted(salaries.values(), key=lambda s: -s["total"])
    if extra:
        out.append(extra)
    for src in out:
        src["total"] = round(src["total"], 2)
        src["label"] = f'{src["kind"]} {src["who"]}'.strip()
    return out


def member_breakdown_from_rows(rows: list, type_: str) -> list:
    """סכום לכל בן משפחה. נגזר רק לסוגים שהמשפחה הפעילה בהם שיוך.

    מקובץ לפי user_id ולא לפי שם — כך הצבע של כל בן משפחה נשאר קבוע גם
    אם שניים חולקים שם פרטי. עסקאות ללא בעלים נאספות יחד תחת "משותפת"."""
    members: dict = {}
    for row in _household_rows(rows):
        if row["type"] != type_:
            continue
        uid = row.get("user_id")
        profile = row.get("profiles")
        name = first_name(profile["name"]) if profile and profile.get("name") else "משותפת"
        key = uid or "__shared__"
        if key not in members:
            members[key] = {"user_id": uid, "name": name, "expense": 0.0}
        members[key]["expense"] += float(row["amount"])
    return sorted(members.values(), key=lambda x: x["expense"], reverse=True)


def project_breakdown_from_rows(rows: list) -> list:
    """מקבצת את עסקאות הפרויקטים של החודש לפי פרויקט.

    הסעיף הציג רשימה שטוחה של כל עסקאות הפרויקטים יחד, כך שבחודש עם
    שיפוץ וטיול העין לא יכלה להפריד ביניהם — וזו בדיוק השאלה ("כמה עלה
    לי השיפוץ החודש?"). כאן כל פרויקט הוא שורה.

    מקובץ לפי **מזהה** ולא לפי שם: שני פרויקטים יכולים להיקרא אותו דבר,
    וקיבוץ לפי שם היה מאחד להם את הכסף — אותו באג בדיוק שהיה בפילוח
    הקטגוריות.

    כל סוג נשמר בנפרד ולא מקוזז לסכום אחד: פרויקט עם החזר כספי היה מוצג
    כ"עלה פחות", ו-₪0 על פרויקט שגם הוציא וגם קיבל הוא מספר שמסתיר את
    שני הצדדים. המיון הוא לפי מה שיצא בפועל.
    """
    by_project = {}
    for row in rows:
        key = row.get("project_id")
        if not key:
            continue
        entry = by_project.setdefault(key, {
            "project_id":   key,
            "name":         row.get("project_name") or "פרויקט",
            "icon":         row.get("project_icon") or "🎯",
            "expense": 0.0, "income": 0.0, "savings": 0.0,
            "transactions": [],
        })
        if row["type"] in ("expense", "income", "savings"):
            entry[row["type"]] += float(row["amount"])
        entry["transactions"].append(row)

    out = []
    for entry in by_project.values():
        for kind in ("expense", "income", "savings"):
            entry[kind] = round(entry[kind], 2)
        entry["outflow"] = round(entry["expense"] + entry["savings"], 2)
        out.append(entry)

    out.sort(key=lambda e: (e["outflow"], e["income"]), reverse=True)
    return out


def category_filter_chips(transactions: list) -> dict:
    """שורת הקטגוריות שנפתחת מתחת ל"הוצאות"/"הכנסות"/"חיסכון" ב"כל העסקאות"
    (מתן, 30.9 — אפשרות א): לכל סוג, הקטגוריות שהיו בו החודש עם הסכום,
    מהגדולה לקטנה.

    כל עסקה מקבלת ‎cat_key‎ — המפתח שהדפדפן מסנן לפיו. לפי מזהה ולא לפי
    שם, כמו כל פילוח בעמוד; קטגוריית פרויקט מקבלת קידומת כדי שלא תתערבב
    בקטגוריה רגילה."""
    groups = {}
    for tx in transactions:
        if tx.get("category_id"):
            key = str(tx["category_id"])
        elif tx.get("project_category_id"):
            key = f"pc-{tx['project_category_id']}"
        else:
            key = "none"
        tx["cat_key"] = key
        chip = groups.setdefault(tx.get("type"), {}).setdefault(key, {
            "key": key, "name": tx.get("category_name") or _NO_CATEGORY,
            "icon": tx.get("category_icon") or "📦", "total": 0.0})
        chip["total"] += float(tx.get("amount") or 0)
    return {t: sorted(({**c, "total": round(c["total"], 2)} for c in by.values()),
                      key=lambda c: (-c["total"], c["name"]))
            for t, by in groups.items()}


def month_transactions_from_rows(rows: list, settings: dict = None,
                                 viewer_user_id: str = None) -> list:
    """רשימת העסקאות להצגה: כוללת פרויקטים, מסתירה פרויקט אישי של אחר."""
    return _format_transactions(
        _filter_hidden_personal_projects(rows, viewer_user_id), settings)


def monthly_trend(archive: list, num_months: int = 12, today=None) -> list:
    """גרף המגמה בעמוד ההשוואה — נגזר מטבלת הארכיון שמתחתיו, ולא נשלף בנפרד.

    הוא נשלף בנפרד עד היום, ושלוש פעמים הסכים עם הטבלה רק בערך: פעם שכח
    להחריג פרויקטים (יולי ₪31,400 בגרף, ₪9,400 בטבלה), פעם נעצר ב"היום"
    והשמיט את שכר הדירה של ה-30 בחודש הנוכחי, ופעם שלף אלפי עסקאות
    שנחתכו ב-‎max_rows‎. עכשיו זה אותו מקור, אז הם לא יכולים להיפרד.

    רק 12 החודשים שעד החודש הנוכחי: תשלום ששולם מראש לנובמבר לא יוצר
    עמודה ב"12 החודשים האחרונים". מהישן לחדש, כמו שהגרף מצייר."""
    hebrew_months = ["", "ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
                     "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]
    today = today or clock.today()
    last = today.year * 12 + today.month - 1
    first = last - num_months + 1

    trend = []
    for m in archive or []:
        y, mo = int(m["year"]), int(m["month"])
        if not first <= y * 12 + mo - 1 <= last:
            continue
        trend.append({
            "key":        f"{y}-{mo:02d}",
            "year":       y,
            "month":      mo,
            "month_name": hebrew_months[mo],
            **{k: round(float(m.get(k) or 0), 2) for k in ("income", "expense", "savings")},
        })
    trend.sort(key=lambda t: t["key"])
    return trend


_SHORT_MONTHS = ["", "ינו׳", "פבר׳", "מרץ", "אפר׳", "מאי", "יוני",
                 "יולי", "אוג׳", "ספט׳", "אוק׳", "נוב׳", "דצמ׳"]
_FULL_MONTHS = ["", "ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
                "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]


def category_trend(family_id: str, months: list, categories: list, today=None) -> dict:
    """כרטיס "לפי קטגוריה" בעמוד ההשוואה (מתן, 30.9): כמה יצא על כל קטגוריה
    בכל אחד מ-‎months‎ — אותם חודשים כמו הגרף שמעליו, מהישן לחדש.

    הוצאות הבית בלבד (בלי פרויקטים), כמו כל סיכום חודשי. ממוצע והחודש הכי
    יקר — מהחודשים שנגמרו: החודש הנוכחי עוד לא נגמר, והוא היה מוריד את
    הממוצע ונראה "חסכוני" בכל אמצע חודש. קטגוריה בלי אף שקל בחלון — בחוץ."""
    today = today or clock.today()
    if not months:
        return {"months": [], "categories": []}
    client = get_client()
    if not client:
        return {"months": [], "categories": []}
    (y0, m0), (y1, m1) = months[0], months[-1]
    try:
        rows = _fetch_all(lambda: client.table("transactions")
                          .select("id, amount, category_id, date, description")
                          .eq("family_id", family_id)
                          .eq("type", "expense")
                          .is_("project_id", "null")
                          .gte("date", f"{y0}-{m0:02d}-01")
                          .lt("date", _next_month(y1, m1))
                          .order("id"))
    except Exception as e:
        raise DataUnavailable("category_trend") from e

    index = {(y, m): i for i, (y, m) in enumerate(months)}
    names = {c["id"]: c for c in categories}
    totals, items = {}, {}
    for r in rows:
        d = str(r["date"])
        i = index.get((int(d[:4]), int(d[5:7])))
        if i is None:
            continue
        key = r.get("category_id") or "none"
        totals.setdefault(key, [0.0] * len(months))[i] += float(r["amount"])
        # העסקאות עצמן — לחלון שנפתח בנגיעה בעמודה של חודש (מתן, 30.9)
        items.setdefault(key, [[] for _ in months])[i].append(
            {"date": d[:10], "description": r.get("description") or "", "amount": float(r["amount"])})

    finished = [i for i, (y, m) in enumerate(months) if (y, m) < (today.year, today.month)]
    out = []
    for key, vals in totals.items():
        vals = [round(v, 2) for v in vals]
        cat = names.get(key) or {}
        done = [vals[i] for i in finished]
        top = max(finished, key=lambda i: vals[i]) if finished else None
        out.append({
            "key": key,
            "name": cat.get("name") or _NO_CATEGORY,
            "icon": cat.get("icon") or "📦",
            "values": vals,
            "avg": round(sum(done) / len(done), 2) if done else None,
            "max": vals[top] if top is not None else None,
            "max_label": _FULL_MONTHS[months[top][1]] if top is not None else None,
            # "החודש" רק כשהחודש האחרון בחלון הוא באמת החודש הנוכחי
            "current": vals[-1] if months[-1] == (today.year, today.month) else None,
            "total": round(sum(vals), 2),
            "items": [sorted(m, key=lambda x: x["date"], reverse=True) for m in items[key]],
        })
    out.sort(key=lambda c: (-c["total"], c["name"]))
    return {"months": [{"year": y, "month": m, "label": _SHORT_MONTHS[m], "name": _FULL_MONTHS[m]}
                       for y, m in months],
            "categories": out}


def category_monthly_averages(family_id: str, today=None) -> dict:
    """ממוצע חודשי לכל קטגוריה, לכל המחלקות — לשורה "בממוצע ₪1,850 בחודש"
    בהגדרות (מתן, 3.10 — רעיון 38). שלושת החודשים **השלמים** האחרונים, מחולק
    ב-3 (כמו ההתראות — ראו ‎get_anomalies‎), בלי פרויקטים. קטגוריה בלי שום
    הוצאה בחלון — לא במילון. זורקת DataUnavailable."""
    today = today or clock.today()
    end = f"{today.year:04d}-{today.month:02d}-01"           # לא כולל החודש הנוכחי
    sm, sy = today.month - _HISTORY_MONTHS, today.year
    while sm <= 0:
        sm += 12
        sy -= 1
    client = get_client()
    if not client:
        raise DataUnavailable("category_monthly_averages: no client")
    try:
        rows = _fetch_all(lambda: client.table("transactions").select("amount, category_id")
                          .eq("family_id", family_id).is_("project_id", "null")
                          .gte("date", f"{sy:04d}-{sm:02d}-01").lt("date", end).order("id"))
    except Exception as e:
        raise DataUnavailable("category_monthly_averages") from e
    totals: dict = {}
    for r in rows:
        if r.get("category_id"):
            totals[str(r["category_id"])] = totals.get(str(r["category_id"]), 0.0) + float(r["amount"])
    return {cid: round(t / _HISTORY_MONTHS) for cid, t in totals.items() if t > 0}


def _category_history_averages(family_id: str, year: int, month: int):
    """השאילתה של get_anomalies: מחזירה
    (current, history, labels) — סכום החודש הנוכחי לכל קטגוריית הוצאה,
    וההיסטוריה החודשית שלה בשלושת החודשים הקודמים (לחישוב ממוצע).
    המפתח הוא מזהה הקטגוריה (ראו ‎category_breakdown_from_rows‎), ו-labels
    ממפה אותו לשם ולאייקון שמוצגים בהתראה.
    ממוטב-לבקשה: שני הקוראים רצים באותו עמוד — השאילתה רצה פעם אחת."""
    return _request_cache(
        f"cat_history:{family_id}:{year}:{month}",
        lambda: _fetch_category_history_averages(family_id, year, month))


# כמה חודשים אחורה נכללים בממוצע. הקבוע יושב כאן כי גם השליפה וגם
# החישוב חייבים להסכים עליו — אחרת "ממוצע שלושת החודשים" מחושב על
# חלון אחר ממה שנשלף.
_HISTORY_MONTHS = 3


def _fetch_category_history_averages(family_id: str, year: int, month: int):
    client = get_client()
    if not client:
        return {}, {}, {}

    start_month, start_year = month - _HISTORY_MONTHS, year
    while start_month <= 0:
        start_month += 12
        start_year  -= 1

    result = client.table("transactions") \
        .select("amount, date, category_id, categories(name, icon)") \
        .eq("family_id", family_id) \
        .eq("type", "expense") \
        .is_("project_id", "null") \
        .gte("date", f"{start_year}-{start_month:02d}-01") \
        .lt("date", _next_month(year, month)) \
        .execute()

    current_key = f"{year}-{month:02d}"
    current: dict = {}
    history: dict = {}   # category_id -> {month_key -> total}
    labels: dict = {}

    for row in result.data:
        cat = row.get("categories") or {}
        cid = row.get("category_id")
        labels[cid] = {"name": cat.get("name") or _NO_CATEGORY,
                       "icon": cat.get("icon") or "📦"}
        key = row["date"][:7]
        if key == current_key:
            current[cid] = current.get(cid, 0) + float(row["amount"])
        else:
            history.setdefault(cid, {})
            history[cid][key] = history[cid].get(key, 0) + float(row["amount"])

    return current, history, labels


def get_anomalies(family_id: str, year: int, month: int, summary: dict,
                  settings: dict = None, skip_categories=None) -> list:
    """Flags unusual data for the month:
    - expense categories running above the family's threshold vs their
      3-previous-months average (percent + minimum gap from settings)
    - expenses exceeding income
    - negative checking-account balance (עו"ש)
    Returns a list of {"severity": "warning"|"danger", "text": str}."""
    cfg = (settings or DEFAULT_FAMILY_SETTINGS).get("anomaly", {})
    if not cfg.get("enabled", True):
        return []
    ratio   = float(cfg.get("percent", 150)) / 100.0
    min_gap = float(cfg.get("min_gap", 300))

    alerts = []

    if summary.get("income", 0) > 0 and summary.get("expense", 0) > summary["income"]:
        alerts.append({
            "severity": "danger",
            "text": f'ההוצאות החודש (₪{format_money(summary["expense"])}) גבוהות מההכנסות (₪{format_money(summary["income"])})',
        })
    # רק כשיש הכנסות, ולפי המספר המעוגל — אותו כלל כמו המאזן שמוצג: בלי
    # הכנסות הוא "—" ולא גירעון (מתן, 30.9), ו-40 אגורות מוצגות ‎₪0‎
    elif summary.get("income", 0) > 0 and round(summary.get("remaining", 0)) < 0:
        alerts.append({
            "severity": "danger",
            "text": "מאזן החודש שלילי — ההוצאות והחיסכון עברו את ההכנסות",
        })

    try:
        current, history, labels = _category_history_averages(family_id, year, month)
        skip = set(skip_categories or ())
        for cid, total in current.items():
            # לקטגוריה עם תקציב יש כבר התראה משלה, מדויקת יותר. שתי
            # התראות על אותה קטגוריה הן רעש, והן גם סותרות: "40% מעל
            # הממוצע" ליד "בתוך התקציב" מבלבל יותר משהוא מסביר.
            if cid in skip:
                continue
            past = history.get(cid)
            if not past:
                continue
            # מחלקים ב-3 ולא ב-‎len(past)‎, כי "ממוצע שלושת החודשים
            # האחרונים" הוא בדיוק זה: חודש בלי הוצאה בקטגוריה הוא ₪0
            # ולא חודש שלא קרה.
            #
            # ‎len(past)‎ עשה שני נזקים הפוכים: תשלום שנתי בודד (ביטוח
            # ₪3,600 ביולי) הפך ל"ממוצע ₪3,600", וכל אוגוסט נראה תקין
            # לנצח; ומנגד ₪50 בחודש אחד בלבד הפכו ₪400 ל"700% מעל
            # הממוצע" — התראה על קטגוריה שאין עליה שום היסטוריה.
            avg = sum(past.values()) / _HISTORY_MONTHS
            if avg > 0 and total > avg * ratio and total - avg >= min_gap:
                pct = round((total / avg - 1) * 100)
                label = labels[cid]
                alerts.append({
                    "severity": "warning",
                    "text": f'{label["icon"]} ההוצאה על {label["name"]} (₪{format_money(total)}) גבוהה ב-{pct}% מהממוצע (₪{format_money(avg)})',
                })
    except Exception:
        logger.exception("get_anomalies")

    return alerts


def budget_alerts(breakdown: list) -> list:
    """התראות על קטגוריות שעברו את התקציב.

    ‎budget_alert‎ היה בעבר החלטה נפרדת מ"יש תקציב", עם תיבת סימון
    משלה. בפועל זו הבחנה בלי הבדל — מי שטרח להגדיר תקציב רוצה לדעת
    כשחרג ממנו, אחרת הוא רק מספר על המסך — והתיבה ירדה. השדה נשאר
    בנתונים, עם ברירת מחדל ‎True‎ (ראו ‎category_budget‎), כדי שתקציבים
    שנשמרו בכתיב הישן ימשיכו להתנהג נכון."""
    out = []
    for row in breakdown:
        if not (row.get("budget_over") and row.get("budget_alert")):
            continue
        out.append({
            "severity": "warning",
            "text": (f'{row.get("icon") or "📦"} {row["name"]}: '
                     f'₪{format_money(row["total"])} מתוך תקציב של ₪{format_money(row["budget"])} '
                     f'— חריגה של ₪{format_money(row["budget_excess"])}'),
        })
    return out


# ─── Family members ───────────────────────────────────────────────────────────

def _fetch_family_members(family_id: str) -> list:
    client = get_client()
    if not client:
        return []
    try:
        result = client.rpc("get_family_members", {"p_family_id": family_id}).execute()
        members = result.data or []
        for m in members:
            m["full_name"] = m.get("name", "")
            m["name"] = first_name(m.get("name", ""))
        return members
    except Exception as e:
        logger.exception("get_family_members")
        raise DataUnavailable("_fetch_family_members") from e


def get_family_members(family_id: str) -> list:
    """ממוטב-לבקשה (ראה _request_cache) — נקרא כמה פעמים בעמוד אחד."""
    return _request_cache(f"members:{family_id}", lambda: _fetch_family_members(family_id))


def update_family_name(family_id: str, name: str):
    client = get_client()
    if not client:
        return False
    try:
        result = client.table("families").update({"name": name}).eq("id", family_id).execute()
        _invalidate_family_cache(family_id)
        # ראו update_category: "נשמר" על שום שורה הוא שקר קטן שמצטבר.
        return bool(result.data)
    except Exception:
        logger.exception("update_family_name")
        return False


def _fetch_family(family_id: str) -> dict:
    client = get_client()
    if not client:
        return {}
    try:
        result = client.table("families").select("*").eq("id", family_id).single().execute()
        return result.data or {}
    except Exception as e:
        # {} מתמזג לברירות המחדל, והעסקה נרשמת על שם של בן משפחה אחר
        raise DataUnavailable("family") from e


def get_family(family_id: str) -> dict:
    """ממוטב-לבקשה (ראה _request_cache) — נקרא גם ישירות וגם דרך ההעדפות."""
    return _request_cache(f"family:{family_id}", lambda: _fetch_family(family_id))


def family_name_for_code(code: str):
    """שם המשפחה שמאחורי קוד הזמנה, או None אם הקוד לא קיים — לתצוגה מקדימה
    ("מצטרפים למשפחת כהן?") לפני שהמשתמש מאשר."""
    client = get_client()
    if not client or not code:
        return None
    try:
        result = client.rpc("family_name_for_code", {"p_code": code}).execute()
        return result.data or None
    except Exception:
        logger.exception("family_name_for_code")
        return None


def family_transaction_count(family_id: str) -> int:
    """כמה תנועות יש למשפחה. משמש כדי להזהיר לפני מעבר למשפחה אחרת: התנועות
    נשארות קשורות למשפחה הישנה דרך transactions.family_id, כך שמי שעוזב
    משפחה עם היסטוריה מאבד אליה את הגישה."""
    client = get_client()
    if not client:
        return 0
    try:
        result = client.table("transactions") \
            .select("id", count="exact") \
            .eq("family_id", family_id) \
            .limit(1).execute()
        return result.count or 0
    except Exception as e:
        # 0 נקרא כ"אין מה לאבד" ומדלג על אישור נטישת המשפחה
        raise DataUnavailable("family_transaction_count") from e


def join_family_by_code(code: str):
    """מצרפת את המשתמש המחובר למשפחה לפי קוד הזמנה.

    עוברת דרך RPC עם security definer ולא ב-SELECT ישיר: מדיניות ה-RLS
    families_member_read מתירה לקרוא משפחה רק לחבר קיים בה, ומצטרף חדש
    מעצם הגדרתו עוד לא חבר — לכן בדיקה ישירה תמיד נכשלת. ראו את המיגרציה
    20260914120000_family_invite_code.sql.

    מחזירה (family_id, error). error הוא None בהצלחה, ומחרוזת בעברית אחרת —
    כדי שהקריאה למעלה תוכל להבחין בין "הצטרפת" ל"הקוד שגוי" במקום לבלוע."""
    client = get_client()
    if not client:
        return None, "בסיס הנתונים אינו זמין כרגע"
    if not code or not code.strip():
        return None, "לא הוזן קוד הזמנה"
    try:
        result = client.rpc("join_family_by_code", {"p_code": code}).execute()
        family_id = result.data
        if not family_id:
            # "או שפג תוקפו": קוד תקף שבוע, ומי שקיבל קוד ישן בדק שוב ושוב
            # שהעתיק נכון. בלי להבחין בין השניים — "פג" היה מאשר לזר שניחש
            # שהקוד היה אמיתי פעם.
            return None, "הקוד לא נמצא או שפג תוקפו — בקשו ממנהל המשפחה קוד חדש"
        return family_id, None
    except Exception:
        logger.exception("join_family_by_code")
        return None, "ההצטרפות נכשלה — נסו שוב בעוד כמה רגעים"


# ─── Archive (months list) ────────────────────────────────────────────────────

def get_months_archive(family_id: str) -> list:
    """Returns a list of {year, month, income, expense, savings, balance} dicts."""
    client = get_client()
    if not client:
        return []
    try:
        result = client.rpc("get_months_archive", {"p_family_id": family_id}).execute()
        return result.data or []
    except Exception as e:
        logger.exception("get_months_archive")
        raise DataUnavailable("get_months_archive") from e


# ─── Helpers ──────────────────────────────────────────────────────────────────

def first_name(full_name: str) -> str:
    """Family members share a surname, so the UI shows first names only."""
    return (full_name or "").strip().split(" ")[0]


def _empty_summary():
    return {"income": 0.0, "expense": 0.0, "savings": 0.0, "balance": 0.0,
            "remaining": 0.0, "expense_pct": 0}


def _next_month(year: int, month: int) -> str:
    if month == 12:
        return f"{year + 1}-01-01"
    return f"{year}-{month + 1:02d}-01"


def _format_transactions(rows: list, settings: dict = None) -> list:
    cfg = settings or DEFAULT_FAMILY_SETTINGS
    # מקום עבודה נשען על שיוך ההכנסה לבן משפחה — בלי שיוך הכנסות אין את מי להציג
    show_workplace = (cfg.get("show_workplace", True)
                      and cfg.get("owner_attribution", {}).get("income", True))
    out = []
    for row in rows:
        # עסקה המשויכת לפרויקט משתמשת בקטגוריה הייעודית שלו (project_categories),
        # לא בקטגוריות הרגילות של המשפחה
        if row.get("project_category_id"):
            cat = row.get("project_categories") or {}
        else:
            cat = row.get("categories") or {}
        user = row.get("profiles") or {}
        proj = row.get("projects") or {}
        out.append({
            "id":                   row["id"],
            "type":                 row["type"],
            "amount":               float(row["amount"]),
            "description":          row.get("description") or "",
            "date":                 str(row["date"]),
            "category_id":          row.get("category_id"),
            "project_category_id":  row.get("project_category_id"),
            "category_name":        cat.get("name", "אחר"),
            "category_icon":        cat.get("icon", "📦"),
            "user_id":              row.get("user_id"),
            "user_name":            first_name(user.get("name", "")) if row.get("user_id") else "משותפת",
            # מיקום העבודה מוצג רק על הכנסות משכורת, ורק אם המשפחה בחרה בכך.
            # מעדיפים תיעוד קפוא על העסקה עצמה (row.workplace) — כדי ששינוי
            # מקום עבודה עתידי לא ישנה בטעות היסטוריה; NULL (עסקאות ישנות
            # מלפני התכונה) נופל חזרה לחיפוש חי מהפרופיל כמו קודם.
            "workplace":            ((row.get("workplace") or user.get("workplace"))
                                     if show_workplace and row["type"] == "income"
                                        and "משכורת" in cat.get("name", "")
                                     else None),
            "is_recurring":         row.get("is_recurring", False),
            "recurring_frequency":  row.get("recurring_frequency"),
            "recurring_end_date":   str(row["recurring_end_date"]) if row.get("recurring_end_date") else None,
            # מזהה התבנית הקבועה שיצרה את המופע הזה (None אם זו עסקה רגילה
            # או תבנית בעצמה) — משמש לסנכרון חכם: הצעה לעדכן גם את התבנית
            # כשמשנים סכום במופע.
            "recurring_parent_id":  row.get("recurring_parent_id"),
            "project_id":           row.get("project_id"),
            # מי *רשם* את העסקה (לא של מי הכסף — זה ‎user_id‎). ‎None‎ = לא ידוע.
            "created_by":           row.get("created_by"),
            "project_name":         proj.get("name"),
            "project_icon":         proj.get("icon"),
            "has_receipt":          bool(row.get("receipt_path")),
            # מופע צפוי בחודש עתידי (‎projected_month_rows‎) — אין עסקה במסד
            "projected":            bool(row.get("projected")),
        })
    return out
