import os
import uuid

from dotenv import load_dotenv
from gotrue.errors import AuthApiError, AuthRetryableError
from postgrest.exceptions import APIError

from . import clock
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
    except Exception as e:
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
    client = get_client()
    if client and access_token:
        try:
            client.postgrest.auth(access_token)
        except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
        logger.exception("fetch_profile(%s)", user_id)
        return None, False


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
            return False, "מספר הטלפון כבר רשום למשתמש אחר"
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
    except Exception as e:
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
    except Exception as e:
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
_WHOLE_MAP_KEYS = frozenset({"limits"})


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
    """ממזג עדכון חלקי לתוך ההגדרות השמורות של המשפחה."""
    client = get_client()
    if not client or not family_id:
        return False
    try:
        stored = (get_family(family_id) or {}).get("settings") or {}
        merged = _merge_settings(stored, patch)
        client.table("families").update({"settings": merged}).eq("id", family_id).execute()
        _invalidate_family_cache(family_id)
        return True
    except Exception as e:
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
    יתאפסו באותו רגע — השרת עצמו רץ ב-UTC."""
    today = clock.today()
    return f"{today.year}-{today.month:02d}-01"


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
    except Exception as e:
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
    import httpx

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key or not path:
        return
    try:
        httpx.request(
            "DELETE",
            f"{url}/storage/v1/object/receipts",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"prefixes": [path]},
            timeout=10,
        )
    except Exception as e:
        logger.exception("delete_receipt")


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
                return None, "לא הצלחתי לקרוא את הקבלה — נסה שוב או הזן ידנית"
            return {
                "amount":         amount,
                "merchant":       (data.get("merchant") or "").strip(),
                "date":           (data.get("date") or "").strip() or None,
                "category_name":  (data.get("category_name") or "").strip() or None,
            }, None
        return None, "לא הצלחתי לקרוא את הקבלה — נסה שוב או הזן ידנית"
    except Exception as e:
        logger.exception("scan_receipt")
        return None, "שגיאה בסריקת הקבלה — נסה שוב"


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

        summary = _empty_summary()
        for row in result.data:
            t = row["type"]
            if t in summary:
                summary[t] += float(row["amount"])

        summary["balance"]   = summary["income"] - summary["expense"]
        # יתרת עו"ש: מה שנשאר בחשבון אחרי הוצאות והפרשות לחיסכון
        summary["remaining"] = summary["income"] - summary["expense"] - summary["savings"]
        total = summary["income"] or 1
        summary["expense_pct"] = round((summary["expense"] / total) * 100)
        return summary
    except Exception as e:
        # לא מחזירים אפסים: דשבורד של ₪0 נראה כמו תקציב ריק ולא כמו תקלה
        raise DataUnavailable("get_monthly_summary") from e


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
        return []


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
        return []


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


def get_recurring_transactions(family_id: str, settings: dict = None) -> list:
    """Returns all recurring transactions for the family."""
    client = get_client()
    if not client:
        return []
    try:
        result = client.table("transactions") \
            .select("*, categories(name, icon), project_categories(name, icon), profiles(name, workplace)") \
            .eq("family_id", family_id) \
            .eq("is_recurring", True) \
            .order("amount", desc=True) \
            .execute()
        return _format_transactions(result.data, settings)
    except Exception as e:
        logger.exception("get_recurring_transactions")
        return []


# כמה פעמים בחודש מתרחשת כל תדירות. שבועי הוא 52/12 ולא 4, ודו-שבועי
# 26/12 ולא 2 — ההפרש הוא כמעט חודש שלם בשנה, ועל שכירות זה סכום אמיתי.
_PER_MONTH = {
    "monthly_same": 1.0, "monthly_1": 1.0, "monthly_15": 1.0,
    "weekly": 52 / 12, "biweekly": 26 / 12,
}


def summarise_recurring(rows: list, today=None) -> dict:
    """מסכם את העסקאות הקבועות לתמונה חודשית.

    מחזיר ‎{"expense": …, "income": …, "savings": …, "rows": [...]}‎ —
    (‎rows‎ ולא ‎items‎: ב-Jinja ‎fixed.items‎ מחזיר את מתודת המילון.)
    הסכומים מנורמלים לחודש, והפריטים ממוינים מהגדול לקטן.

    זה המספר שמשפחה הכי צריכה ולא יכלה לקבל: ההוצאות הקבועות קיימות
    באפליקציה אבל קבורות באקורדיון סגור בהגדרות, ואין מסך שעונה על
    "כמה יוצא לנו כל חודש בלי קשר למה שנעשה". זה מה שלא משתנה, ולכן
    זה מה שאפשר לתכנן סביבו.

    תבנית שתאריך הסיום שלה עבר לא נספרת — היא כבר לא קבועה."""
    today = today or clock.today()
    totals = {"expense": 0.0, "income": 0.0, "savings": 0.0}
    items = []

    for row in rows:
        end = row.get("recurring_end_date")
        if end and str(end) < today.isoformat():
            continue
        per_month = _PER_MONTH.get(row.get("recurring_frequency") or "monthly_1", 1.0)
        monthly = float(row["amount"]) * per_month
        if row["type"] in totals:
            totals[row["type"]] += monthly
        items.append({**row, "monthly_amount": monthly, "per_month": per_month})

    items.sort(key=lambda r: r["monthly_amount"], reverse=True)
    return {**totals, "rows": items}


def materialize_recurring(family_id: str) -> int:
    """משלים מופעים חסרים של עסקאות קבועות עד היום (כולל רטרואקטיבית).

    כל עסקה שסומנה כקבועה משמשת "תבנית": המופע הראשון הוא העסקה עצמה,
    ומכאן נוצרים מופעים רגילים (is_recurring=False) לפי התדירות, עד היום
    או עד תאריך הסיום. הפונקציה אידמפוטנטית — מופע שכבר קיים לא ייווצר שוב.
    מחזירה ‎(created, ok)‎. ‎ok=False‎ פירושו שהריצה נכשלה — וזה חשוב, כי
    הקורא מסמן "סונכרן להיום" ולא ינסה שוב עד מחר. כשל שנראה כהצלחה
    משאיר חודש בלי משכורת ובלי הוראות קבע עד למחרת."""
    from datetime import date

    client = get_client()
    if not client or not family_id:
        return 0, False
    try:
        templates = client.table("transactions").select("*") \
            .eq("family_id", family_id).eq("is_recurring", True).execute().data
        if not templates:
            return 0, True

        existing = client.table("transactions") \
            .select("recurring_parent_id, date") \
            .eq("family_id", family_id) \
            .not_.is_("recurring_parent_id", "null") \
            .execute().data
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
                    "user_id":             t.get("user_id"),
                    "family_id":           family_id,
                    "is_recurring":        False,
                    "recurring_parent_id": t["id"],
                    # נשמר גם על המופע (לא רק על התבנית) כדי שהתצוגה תוכל
                    # לציין "עסקה קבועה — כל X" בלי לשלוף את התבנית בנפרד
                    "recurring_frequency": t.get("recurring_frequency"),
                    "workplace":           _owner_workplace(t.get("user_id")) if is_salary else None,
                })

        if new_rows:
            try:
                client.table("transactions").insert(new_rows, returning="minimal").execute()
            except Exception as e:
                # כשל ייחודיות = בקשה מקבילה כבר יצרה את המופעים — תקין
                if "uq_tx_recurring_occurrence" in str(e) or "23505" in str(e):
                    return 0, True
                raise
        return len(new_rows), True
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


def update_recurring_template(template_id: str, family_id: str, amount: float = None,
                              category_id: str = None, description: str = None):
    """סנכרון חכם: מעדכן רק את התבנית הקבועה עצמה (לא נוגע ב-date/type/תדירות),
    כדי שרק מופעים עתידיים שעוד לא נוצרו ישתמשו בערך החדש — היסטוריה לא נכתבת מחדש.
    Returns (updated_row, error)."""
    client = get_client()
    if not client:
        return None, "Database not configured"

    patch = {}
    if amount is not None:
        patch["amount"] = amount
    if category_id is not None:
        patch["category_id"] = category_id
    if description is not None:
        patch["description"] = description
    if not patch:
        return None, "אין שדות לעדכון"

    try:
        result = client.table("transactions") \
            .update(patch) \
            .eq("id", template_id) \
            .eq("family_id", family_id) \
            .eq("is_recurring", True) \
            .execute()
        return (result.data[0] if result.data else None), None
    except Exception as e:
        return None, str(e)


def remove_family_member(user_id: str, keep_transactions: bool = True):
    """מסירה בן משפחה. מנהל המשפחה בלבד. מחזירה (ok, error).

    הכללים נאכפים ב-DB ולא כאן: הפונקציה נגזרת מ-auth.uid(), בודקת שהקורא
    הוא המנהל ושהיעד אכן במשפחה שלו, ומסרבת להסיר את המנהל עצמו — אחרת שני
    חברים היו יכולים להסיר זה את זה עד שלא נשאר אף אחד."""
    client = get_client()
    if not client:
        return False, "Database not configured"
    try:
        client.rpc("remove_family_member",
                   {"p_user_id": user_id, "p_keep_transactions": keep_transactions}).execute()
        return True, None
    except Exception as e:
        logger.exception("remove_family_member")
        return False, str(e)


def leave_family(keep_transactions: bool = True):
    """עוזבת את המשפחה הנוכחית ופותחת משפחה חדשה וריקה.
    מחזירה (new_family_id, error)."""
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        result = client.rpc("leave_family",
                            {"p_keep_transactions": keep_transactions}).execute()
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


def rotate_invite_code():
    """מחליפה את קוד ההזמנה. מחזירה (new_code, error).
    כל בן משפחה רשאי — מי שמגלה שהקוד דלף צריך לסגור אותו מיד."""
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
        row = client.table("transactions") \
            .select("id, date, is_recurring, recurring_parent_id") \
            .eq("id", transaction_id).eq("family_id", family_id) \
            .maybe_single().execute().data
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
        row = client.table("transactions").select("type") \
            .eq("id", transaction_id).eq("family_id", family_id) \
            .maybe_single().execute().data
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
        row = client.table("transactions").select("recurring_parent_id") \
            .eq("id", transaction_id).eq("family_id", family_id) \
            .maybe_single().execute().data
        return bool(row and row.get("recurring_parent_id"))
    except Exception as e:
        raise DataUnavailable("is_recurring_instance") from e


def delete_one_occurrence(transaction_id: str, template_id: str,
                          occurrence_date: str, family_id: str):
    """מוחקת מופע אחד, ורושמת שדילגו עליו. מחזירה (ok, error).

    הרישום הוא כל העניין: בלעדיו המנוע רואה חודש חסר ומשלים אותו
    בריצה הבאה, כלומר המחיקה מתבטלת מעצמה למחרת."""
    client = get_client()
    if not client:
        return False, "Database not configured"
    try:
        tpl = client.table("transactions").select("recurring_skips") \
            .eq("id", template_id).eq("family_id", family_id) \
            .maybe_single().execute().data
        if tpl is None:
            return False, "not found"

        skips = list(tpl.get("recurring_skips") or [])
        if occurrence_date not in [str(x) for x in skips]:
            skips.append(occurrence_date)

        # הדילוג נרשם **לפני** המחיקה. בסדר ההפוך, כשל בכתיבה היה
        # משאיר מופע מחוק בלי סימן — והוא היה חוזר מחר.
        client.table("transactions").update({"recurring_skips": skips}) \
            .eq("id", template_id).eq("family_id", family_id).execute()

        deleted = client.table("transactions").delete() \
            .eq("id", transaction_id).eq("family_id", family_id) \
            .execute().data or []
        return bool(deleted), None
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
        template = client.table("transactions").select("id, date") \
            .eq("id", template_id).eq("family_id", family_id) \
            .maybe_single().execute().data
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
    client = get_client()
    if not client:
        return False
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
        return bool(result.data)
    except Exception:
        # המשתמש כן רואה "מחיקה נכשלה", אז זה לא כשל שקט — אבל בלי
        # הרישום אי אפשר לענות על "למה".
        logger.exception("delete_transaction")
        return False


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


def bulk_add_categories(family_id: str, categories: list) -> tuple:
    """Inserts multiple categories at once for a family's onboarding.
    `categories` is a list of {name, icon, type} dicts. Returns (count, error).
    sort_order נקבע לפי הסדר ברשימת הקלט (בתוך כל סוג בנפרד) — כך שהסדר
    ההתחלתי תואם למה שהוגדר ב-_DEFAULT_CATEGORIES."""
    client = get_client()
    if not client:
        return 0, "Database not configured"
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
        client.table("categories") \
            .update({"name": name, "icon": icon}) \
            .eq("id", cat_id) \
            .eq("family_id", family_id) \
            .execute()
        return True
    except Exception as e:
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
    except Exception as e:
        logger.exception("reorder_categories")
        return False


# ─── Projects (תקציבי פרויקטים — משותפים או אישיים לבן משפחה אחד) ─────────────

def get_projects(family_id: str, viewer_user_id: str) -> list:
    """פרויקטים גלויים לצופה הנוכחי: כל הפרויקטים המשותפים + הפרויקטים
    האישיים ששייכים לו עצמו. פרויקט אישי של בן משפחה אחר לא נכלל כאן בכלל —
    זו הפרטיות המבוקשת (לא רק מוסתר בתצוגה, אלא לא נשלף כלל)."""
    client = get_client()
    if not client or not family_id:
        return []
    try:
        projects = client.table("projects").select("*") \
            .eq("family_id", family_id).eq("archived", False) \
            .order("created_at", desc=True).execute().data
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
            })
        return out
    except Exception as e:
        logger.exception("get_projects")
        return []


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


def update_project(project_id: str, family_id: str, name: str, budget_target: float = None,
                   description: str = None, icon: str = None, track_expense: bool = True,
                   track_income: bool = False, track_savings: bool = False):
    """מעדכן שם/יעד/סוגי מעקב בלבד. שינוי בעלות (אישי/משותף) נעשה רק דרך
    share_project/unshare_project הייעודיות — לא כאן."""
    client = get_client()
    if not client:
        return False
    try:
        existing = client.table("projects") \
            .select("track_expense, track_income, track_savings") \
            .eq("id", project_id).eq("family_id", family_id).single().execute().data or {}
        # סוגים שהופעלו כרגע לראשונה — נזרע להם קטגוריות התחלתיות
        newly_enabled = [
            t for t, before, after in (
                ("expense", existing.get("track_expense"), track_expense),
                ("income", existing.get("track_income"), track_income),
                ("savings", existing.get("track_savings"), track_savings),
            ) if after and not before
        ]

        client.table("projects").update({
            "name": name, "budget_target": budget_target, "description": description,
            "icon": icon, "track_expense": track_expense, "track_income": track_income,
            "track_savings": track_savings,
        }).eq("id", project_id).eq("family_id", family_id).execute()

        if newly_enabled:
            _seed_project_categories(project_id, family_id, newly_enabled)
        return True
    except Exception as e:
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
        proj = client.table("projects").select("owner_id") \
            .eq("id", project_id).eq("family_id", family_id).single().execute().data
        if not proj:
            return False, "הפרויקט לא נמצא"
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
        proj = client.table("projects").select("owner_id, created_by") \
            .eq("id", project_id).eq("family_id", family_id).single().execute().data
        if not proj:
            return False, "הפרויקט לא נמצא"
        if proj.get("owner_id"):
            return False, "הפרויקט כבר אישי"
        if proj.get("created_by") != user_id:
            return False, "רק מי שיצר את הפרויקט יכול להחזיר אותו להיות אישי"
        client.table("projects").update({"owner_id": user_id}) \
            .eq("id", project_id).eq("family_id", family_id).execute()
        return True, None
    except Exception as e:
        return False, str(e)


def delete_project(project_id: str, family_id: str, delete_transactions: bool = False) -> bool:
    """מוחק את הפרויקט (וקטגוריותיו הייעודיות, ON DELETE CASCADE).

    delete_transactions=False (ברירת מחדל): העסקאות ששויכו אליו לא נמחקות —
    הן חוזרות להיספר תחת הקטגוריה הרגילה שלהן (ON DELETE SET NULL).
    delete_transactions=True: מוחקים גם את כל העסקאות ששויכו לפרויקט, לפני
    מחיקת הפרויקט עצמו."""
    client = get_client()
    if not client:
        return False
    try:
        if delete_transactions:
            client.table("transactions").delete() \
                .eq("project_id", project_id).eq("family_id", family_id).execute()
        client.table("projects").delete() \
            .eq("id", project_id).eq("family_id", family_id).execute()
        return True
    except Exception as e:
        logger.exception("delete_project")
        return False


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
    try:
        proj = client.table("projects").select("*") \
            .eq("id", project_id).eq("family_id", family_id).single().execute().data
        if not proj:
            return None
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
        return None


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
    except Exception as e:
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
        return []


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


def update_project_category(cat_id: str, project_id: str, family_id: str, name: str, icon: str):
    client = get_client()
    if not client:
        return False
    try:
        client.table("project_categories").update({"name": name, "icon": icon}) \
            .eq("id", cat_id).eq("project_id", project_id).eq("family_id", family_id).execute()
        return True
    except Exception as e:
        logger.exception("update_project_category")
        return False


def delete_project_category(cat_id: str, project_id: str, family_id: str) -> bool:
    client = get_client()
    if not client:
        return False
    try:
        client.table("project_categories").delete() \
            .eq("id", cat_id).eq("project_id", project_id).eq("family_id", family_id).execute()
        return True
    except Exception as e:
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


def month_transactions_from_rows(rows: list, settings: dict = None,
                                 viewer_user_id: str = None) -> list:
    """רשימת העסקאות להצגה: כוללת פרויקטים, מסתירה פרויקט אישי של אחר."""
    return _format_transactions(
        _filter_hidden_personal_projects(rows, viewer_user_id), settings)


def get_monthly_trend(family_id: str, num_months: int = 6) -> list:
    """Returns income/expense/savings totals for the last N months."""
    client = get_client()
    if not client:
        return []
    try:
        today  = clock.today()
        # Calculate start date (first day of N months ago)
        start_month = today.month - num_months + 1
        start_year  = today.year
        while start_month <= 0:
            start_month += 12
            start_year  -= 1
        start_date = f"{start_year}-{start_month:02d}-01"

        # אותה החרגה בדיוק כמו get_monthly_summary ו-get_months_archive:
        # עסקה המשויכת לפרויקט היא הוצאה חד-פעמית/הונית שמעוותת את תמונת
        # ה"חודש הרגיל", ולכן היא מוחרגת מהמאזן החודשי בכל מקום.
        # כאן זה נשכח, ולכן הגרף והטבלה באותו עמוד הציגו שני מספרים
        # סותרים לאותו חודש — הפרש בגודל הפרויקט, בלי שום הסבר על המסך.
        result = client.table("transactions") \
            .select("type, amount, date") \
            .eq("family_id", family_id) \
            .is_("project_id", "null") \
            .gte("date", start_date) \
            .execute()

        # Aggregate by year+month
        buckets: dict = {}
        for row in result.data:
            d = row["date"][:7]  # "YYYY-MM"
            if d not in buckets:
                buckets[d] = {"income": 0.0, "expense": 0.0, "savings": 0.0}
            t = row["type"]
            if t in buckets[d]:
                buckets[d][t] += float(row["amount"])

        hebrew_months = [
            "", "ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
            "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"
        ]

        trend = []
        for key in sorted(buckets):
            y, m = int(key[:4]), int(key[5:7])
            trend.append({
                "key":        key,
                "year":       y,
                "month":      m,
                "month_name": hebrew_months[m],
                **{k: round(v, 2) for k, v in buckets[key].items()},
            })
        return trend
    except Exception as e:
        logger.exception("get_monthly_trend")
        return []


def _category_history_averages(family_id: str, year: int, month: int):
    """שאילתה משותפת ל-get_anomalies ול-get_run_rate_forecasts: מחזירה
    (current, history, icons) — סכום החודש הנוכחי לכל קטגוריית הוצאה,
    וההיסטוריה החודשית שלה בשלושת החודשים הקודמים (לחישוב ממוצע).
    ממוטב-לבקשה: שני הקוראים רצים באותו עמוד — השאילתה רצה פעם אחת."""
    return _request_cache(
        f"cat_history:{family_id}:{year}:{month}",
        lambda: _fetch_category_history_averages(family_id, year, month))


def _fetch_category_history_averages(family_id: str, year: int, month: int):
    client = get_client()
    if not client:
        return {}, {}, {}

    start_month, start_year = month - 3, year
    while start_month <= 0:
        start_month += 12
        start_year  -= 1

    result = client.table("transactions") \
        .select("amount, date, categories(name, icon)") \
        .eq("family_id", family_id) \
        .eq("type", "expense") \
        .is_("project_id", "null") \
        .gte("date", f"{start_year}-{start_month:02d}-01") \
        .lt("date", _next_month(year, month)) \
        .execute()

    current_key = f"{year}-{month:02d}"
    current: dict = {}
    history: dict = {}   # category -> {month_key -> total}
    icons: dict = {}

    for row in result.data:
        cat  = row.get("categories") or {}
        name = cat.get("name", "אחר")
        icons[name] = cat.get("icon", "📦")
        key  = row["date"][:7]
        if key == current_key:
            current[name] = current.get(name, 0) + float(row["amount"])
        else:
            history.setdefault(name, {})
            history[name][key] = history[name].get(key, 0) + float(row["amount"])

    return current, history, icons


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
            "text": f'ההוצאות החודש (₪{summary["expense"]:,.0f}) גבוהות מההכנסות (₪{summary["income"]:,.0f})',
        })
    elif summary.get("remaining", 0) < 0:
        alerts.append({
            "severity": "danger",
            "text": "יתרת העו\"ש החודש שלילית — ההוצאות והחיסכון עברו את ההכנסות",
        })

    try:
        current, history, icons = _category_history_averages(family_id, year, month)
        skip = set(skip_categories or ())
        for name, total in current.items():
            # לקטגוריה עם תקציב יש כבר התראה משלה, מדויקת יותר. שתי
            # התראות על אותה קטגוריה הן רעש, והן גם סותרות: "40% מעל
            # הממוצע" ליד "בתוך התקציב" מבלבל יותר משהוא מסביר.
            if name in skip:
                continue
            past = history.get(name)
            if not past:
                continue
            avg = sum(past.values()) / len(past)
            if avg > 0 and total > avg * ratio and total - avg >= min_gap:
                pct = round((total / avg - 1) * 100)
                alerts.append({
                    "severity": "warning",
                    "text": f'{icons[name]} ההוצאה על {name} (₪{total:,.0f}) גבוהה ב-{pct}% מהממוצע (₪{avg:,.0f})',
                })
    except Exception as e:
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
                     f'₪{row["total"]:,.0f} מתוך תקציב של ₪{row["budget"]:,.0f} '
                     f'— חריגה של ₪{row["budget_excess"]:,.0f}'),
        })
    return out


def get_run_rate_forecasts(family_id: str, year: int, month: int, settings: dict = None) -> list:
    """תחזית 'קצב ריצה': משליכה את קצב ההוצאה היומי של החודש-עד-כה לסוף
    החודש, ומתריעה מראש (לפני שהחריגה קרתה בפועל) אם ההשלכה חוצה את אותו
    סף שכבר מוגדר בהעדפות המשפחה (get_anomalies). רלוונטי רק לחודש הנוכחי
    שעדיין באמצעו — לא לחודשים שהסתיימו, ולא בימים הראשונים (קצב לא יציב).
    Returns a list of {"severity": "forecast", "text": str}."""
    import calendar

    cfg = (settings or DEFAULT_FAMILY_SETTINGS).get("anomaly", {})
    if not cfg.get("enabled", True):
        return []

    today = clock.today()
    if (year, month) != (today.year, today.month):
        return []
    days_elapsed = today.day
    if days_elapsed < 3:
        return []  # קצב מתחילת חודש רועש מדי להשליך ממנו
    days_in_month = calendar.monthrange(year, month)[1]

    ratio   = float(cfg.get("percent", 150)) / 100.0
    min_gap = float(cfg.get("min_gap", 300))

    forecasts = []
    try:
        current, history, icons = _category_history_averages(family_id, year, month)
        for name, total in current.items():
            past = history.get(name)
            if not past:
                continue
            avg = sum(past.values()) / len(past)
            if avg <= 0:
                continue
            # כבר חרגה בפועל — get_anomalies כבר מתריע, אין צורך בכפילות
            if total > avg * ratio and total - avg >= min_gap:
                continue
            projected = (total / days_elapsed) * days_in_month
            if projected > avg * ratio and projected - avg >= min_gap:
                forecasts.append({
                    "severity": "forecast",
                    "text": f'🔮 בקצב הנוכחי, קטגוריית {icons[name]} {name} צפויה לחרוג ב-₪{(projected - avg):,.0f} מהממוצע (₪{avg:,.0f}) עד סוף החודש',
                })
    except Exception as e:
        logger.exception("get_run_rate_forecasts")

    return forecasts


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
        return []


def get_family_members(family_id: str) -> list:
    """ממוטב-לבקשה (ראה _request_cache) — נקרא כמה פעמים בעמוד אחד."""
    return _request_cache(f"members:{family_id}", lambda: _fetch_family_members(family_id))


def update_family_name(family_id: str, name: str):
    client = get_client()
    if not client:
        return False
    try:
        client.table("families").update({"name": name}).eq("id", family_id).execute()
        _invalidate_family_cache(family_id)
        return True
    except Exception as e:
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
    except Exception as e:
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
            return None, "קוד ההזמנה לא נמצא — בדקו שהועתק במלואו"
        return family_id, None
    except Exception as e:
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
        return []


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
            "user_name":            first_name(user.get("name", "")) if row.get("user_id") else "משותף",
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
            "project_name":         proj.get("name"),
            "project_icon":         proj.get("icon"),
            "has_receipt":          bool(row.get("receipt_path")),
        })
    return out
