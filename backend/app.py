from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g, make_response
from dotenv import load_dotenv
from functools import wraps, partial
from datetime import date, timedelta
from werkzeug.middleware.proxy_fix import ProxyFix
import csv
import hashlib
import io
import json
import math
import os
import re
import time
from . import supabase_config as db
from . import clock
from . import logs

logs.setup()
logger = logs.get("smartfin.app")

load_dotenv()

# ─── ניטור שגיאות ────────────────────────────────────────────────────────────
# בלי זה שגיאה שמשתמש נתקל בה מגיעה ל-error.html ושם נעלמת: ה-print ללוגים של
# Railway נמחק ואף אחד לא קורא אותו. עם משתמש אחד זה נסבל כי הוא מגלה לבד;
# עם מאה זה אומר שמשתמש מתוסכל עוזב ואין לנו מושג למה.
# פעיל רק כש-SENTRY_DSN מוגדר, כך שפיתוח מקומי ופריסות קיימות לא מושפעים.
# שמות משתנים ושדות שאסור שיעזבו את השרת. נבדק מול השם בפועל בקוד:
# password/current_password במסלולי האימות, access_token/refresh_token
# ב-session, image_bytes/b64 בסריקת הקבלה.
_SECRET_NAMES = (
    "password", "passwd", "secret", "token", "authorization", "apikey",
    "api_key", "image_bytes", "b64", "encrypted_password",
)


def _looks_secret(name: str) -> bool:
    return any(s in str(name).lower() for s in _SECRET_NAMES)


def _scrub_event(event, hint):
    """מנקה את האירוע לפני שהוא עוזב את השרת.

    האפליקציה מטפלת בנתונים פיננסיים, ומסלול סריקת הקבלה נושא תמונה של
    קבלה אמיתית — שום אחד מאלה לא אמור להגיע לשירות חיצוני.

    הניקוי הקודם נגע רק ב-event["request"], וזה לא היה מספיק: ה-SDK מצרף
    לכל frame ב-stacktrace גם את המשתנים המקומיים שהיו בזיכרון באותו רגע.
    בפועל זה אומר שחריגה כלשהי במסלול התחברות, הרשמה, איפוס סיסמה או
    מחיקת חשבון הייתה שולחת את הסיסמה עצמה; חריגה ב-inject_auth הייתה
    שולחת את טוקני Supabase; וחריגה בסריקת קבלה הייתה שולחת את התמונה.

    include_local_variables=False כבר מכבה את זה ב-SDK, והניקוי כאן הוא
    השכבה השנייה — בדיוק כמו שההערה המקורית התכוונה, אבל במקומות שבהם
    הנתונים באמת נמצאים: extra, breadcrumbs, contexts ו-query_string,
    שאף אחד מהם לא נגע בהם קודם."""
    request_data = event.get("request") or {}
    request_data.pop("data", None)
    request_data.pop("cookies", None)
    # ה-query string נושא ?code=<קוד הזמנה> ב-/api/family/preview
    request_data.pop("query_string", None)
    headers = request_data.get("headers") or {}
    for sensitive in ("Cookie", "Authorization"):
        headers.pop(sensitive, None)

    # משתנים מקומיים בכל frame — הנתיב שהיה פתוח לגמרי
    for value in (event.get("exception") or {}).get("values") or []:
        for frame in (value.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)

    # extra / contexts: ערכים שהקוד שולח במפורש, היום או בעתיד
    for section in ("extra", "contexts"):
        holder = event.get(section)
        if isinstance(holder, dict):
            for key in list(holder):
                if _looks_secret(key):
                    holder[key] = "[scrubbed]"

    # breadcrumbs: ה-SDK מתעד בהן בקשות ושאילתות שקדמו לשגיאה
    for crumb in event.get("breadcrumbs") or []:
        if not isinstance(crumb, dict):
            continue
        data = crumb.get("data")
        if isinstance(data, dict):
            for key in list(data):
                if _looks_secret(key):
                    data[key] = "[scrubbed]"

    return event


_sentry_dsn = os.environ.get("SENTRY_DSN")
if _sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration

    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[FlaskIntegration()],
        send_default_pii=False,   # בלי כתובות IP, עוגיות או גוף בקשה
        # ברירת המחדל היא True, והיא מה שצירף סיסמאות וטוקנים לכל דיווח
        include_local_variables=False,
        traces_sample_rate=0.0,   # שגיאות בלבד — מדידות ביצועים עולות כסף ולא נחוצות כאן
        environment=os.environ.get("RAILWAY_ENVIRONMENT_NAME", "local"),
        before_send=_scrub_event,
    )


_BASE = os.path.dirname(__file__)
app = Flask(
    __name__,
    template_folder=os.path.join(_BASE, '..', 'frontend', 'templates'),
    static_folder=os.path.join(_BASE, '..', 'frontend', 'static'),
    static_url_path='/static',
)

# מפתח החתימה של ה-sessions חייב להגיע מהסביבה — בלי fallback, אחרת עוגיות
# ניתנות לזיוף עם מפתח ציבורי ידוע. נכשלים בהפעלה במקום להמשיך בשקט.
_secret = os.environ.get("SECRET_KEY")
if not _secret:
    raise RuntimeError("SECRET_KEY environment variable is required — refusing to start without it")
app.secret_key = _secret

# נשארים מחוברים עד יציאה יזומה. העוגייה מוגדרת לעשר שנים — בפועל "תמיד" —
# ו-SESSION_REFRESH_EACH_REQUEST (ברירת המחדל של Flask, מפורש כאן) דוחף את
# תאריך התפוגה קדימה בכל בקשה, כך שמשתמש פעיל לעולם לא מגיע אליו.
# מה שמאפשר את זה בפועל הוא רענון ה-refresh token ב-inject_auth: טוקן הגישה
# של Supabase חי כשעה, וההתחברות שורדת כי הוא מוחלף מעצמו.
app.permanent_session_lifetime = timedelta(days=3650)

# הקשחת עוגיות: העוגייה נושאת את טוקני Supabase, אז Secure חובה בפרודקשן
# (בפיתוח מקומי על http זה היה שובר את ההתחברות — לכן מותנה).
_IS_DEV = os.environ.get("FLASK_ENV") == "development"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",   # גם הגנת CSRF בסיסית
    SESSION_COOKIE_SECURE=not _IS_DEV,
    SESSION_REFRESH_EACH_REQUEST=True,   # חלון התפוגה נע קדימה עם כל שימוש
    PREFERRED_URL_SCHEME="https" if not _IS_DEV else "http",
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,  # תקרת גודל בקשה — מגן על העלאת קבלות
)

# מאחורי ה-proxy של Railway (TLS termination) — כדי ש-request.host_url יחזיר
# https בקישורי איפוס-סיסמה. לא מזיק בפיתוח מקומי.
#
# x_for=1 חיוני ל-rate limiting ולא רק לנוחות: בלעדיו remote_addr הוא צומת
# הקצה של Railway ולא המשתמש. נמדד בפועל — 12 בקשות ממחשב אחד התפצלו על
# ארבע כתובות proxy שונות, כך שהמגבלה לא נאכפה. גרוע מכך, כל המשתמשים
# חולקים את אותן כתובות, ולכן משתמש אחד רועש היה יכול לנעול את ההתחברות
# לכולם.
#
# הערך 2 נמדד ולא נוחש: Railway מוסיף שתי שכבות, ו-X-Forwarded-For מגיע
# כ-"<לקוח>, <צומת קצה>". ProxyFix סופר מימין, כך ש-1 החזיר את צומת
# הקצה ו-2 מחזיר את הלקוח. הספירה מימין היא גם מה שמונע זיוף: ערך
# ש-הלקוח דוחף בעצמו נדחק שמאלה ולעולם לא נבחר.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=2, x_proto=1, x_host=1)

# הגבלת קצב על מסלולי האימות — מונע ניחוש סיסמאות וסריקת מספרי טלפון.
#
# האחסון חייב להיות משותף בפרודקשן. עם "memory://" כל worker של gunicorn
# סופר לעצמו, כך שהמגבלה מוכפלת במספר ה-workers, וכל פריסה מאפסת את המונים —
# כלומר ההגנה על התחברות, הרשמה ואיפוס סיסמה רופפת בהרבה ממה שכתוב בקוד.
# זה היה מספיק כשזו הייתה אפליקציה משפחתית; ברגע שהכתובת מופצת זה לא.
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

_RATELIMIT_STORAGE = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri=_RATELIMIT_STORAGE,
    default_limits=[],  # רק המסלולים שמסומנים במפורש מוגבלים
    # אם האחסון המשותף לא זמין — נופלים למונים מקומיים במקום להחזיר שגיאה.
    # תקלה אצל ספק ה-Redis לא אמורה לנעול לאנשים את ההתחברות לאפליקציה:
    # הגבלה רופפת לכמה דקות עדיפה בהרבה על אתר שאי אפשר להיכנס אליו.
    in_memory_fallback_enabled=True,
)

# אם נשארנו על זיכרון מקומי בפרודקשן — אומרים את זה בקול. הכישלון כאן שקט
# מטבעו: הבקשות ממשיכות לעבוד והמגבלה פשוט לא נאכפת, כך שבלי ההתראה הזאת
# אין שום דרך להבחין בין "מוגן" ל"נראה מוגן".
if _RATELIMIT_STORAGE.startswith("memory://") and not _IS_DEV:
    logger.warning("rate limiting is using in-memory storage in production — "
                   "limits are per-worker and reset on every deploy. "
                   "Set RATELIMIT_STORAGE_URI.")


# ─── נכסים סטטיים: חתימה לפי תוכן ────────────────────────────────────────────
#
# כל קובץ סטטי נשלח עם "no-cache", כלומר הדפדפן חייב לשאול את השרת בכל
# טעינת עמוד אם העותק שלו עדיין תקף. שש שאלות כאלה בכל עמוד, כולן נענות
# "לא השתנה", וכל אחת תופסת אחד משני ה-workers. בפועל שש מתוך שבע הפניות
# בטעינת עמוד רגילה הן שיחה על כלום.
#
# הסיבה היא שלכתובת אין גרסה: /static/css/style.css היא אותה כתובת בין אם
# זה הקובץ של אתמול או של היום, אז לדפדפן אין דרך אחרת לדעת.
#
# הפתרון: ‎?v=<חתימה>‎ שנגזרת מתוכן הקובץ, ותוקף של שנה. הדפדפן לא שואל,
# וכשקובץ משתנה החתימה משתנה איתו — כתובת חדשה, הורדה מחדש, אוטומטית.
#
# החתימה נגזרת מהתוכן ולא ממספר ידני, וזה העיקר: מספר שצריך לזכור לעדכן
# הוא מספר שיישכח, והתוצאה היא דפדפן שמגיש קובץ ישן במשך שנה בלי שום דרך
# לתקן מרחוק. כאן אי אפשר לשכוח.
_ASSET_HASHES: dict = {}


def _asset_version(filename: str) -> str:
    """שמונה תווים מתוך חתימת התוכן של הקובץ. ריק אם הוא לא נמצא."""
    if filename in _ASSET_HASHES:
        return _ASSET_HASHES[filename]

    path = os.path.join(app.static_folder, filename)
    try:
        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()[:8]
    except OSError:
        # קובץ שלא נמצא: לא מפילים את העמוד בגלל נכס חסר. הוא ייכשל
        # בטעינה כמו קודם, וזה מצב שקל לראות.
        digest = ""
    if not _IS_DEV:
        _ASSET_HASHES[filename] = digest
    return digest


@app.context_processor
def _versioned_static():
    """דורס את url_for עבור נכסים סטטיים בלבד.

    דריסה ולא פונקציה חדשה, כדי ש-48 הקריאות הקיימות בתבניות לא ישתנו —
    ובעיקר כדי שקריאה שתיכתב מחר תקבל את זה בלי שאיש יזכור."""
    def versioned_url_for(endpoint, **values):
        if endpoint == "static" and "filename" in values and "v" not in values:
            version = _asset_version(values["filename"])
            if version:
                values["v"] = version
        return url_for(endpoint, **values)
    return {"url_for": versioned_url_for}


@app.after_request
def _cache_static_forever(response):
    """שנה של מטמון, אבל רק לכתובת חתומה.

    בלי החתימה זה היה מסוכן: כתובת בלי גרסה שנשמרת לשנה היא קובץ ישן
    שאין דרך לרענן. עם חתימה, שינוי בקובץ מייצר כתובת אחרת ממילא."""
    if request.endpoint == "static" and request.args.get("v"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


# ─── Auth helpers ─────────────────────────────────────────────────────────────

def _do_not_rewrite_session_cookie():
    """מסמן שהתגובה הזאת לא תכתוב מחדש את עוגיית ה-session.

    זה חשוב בדיוק כשהרענון נכשל. שני ה-workers של gunicorn מקבלים בקשות
    במקביל, וה-refresh token של Supabase מסובב בכל רענון — כך שבקשה אחת
    יכולה לרענן בהצלחה ולכתוב טוקן חדש לעוגייה, בעוד בקשה מקבילה, שיצאה
    עם הטוקן הישן ונתקעה על רשת סלולרית איטית, מגיעה אחריה ונכשלת. אם
    הבקשה הכושלת תכתוב את העוגייה שלה, היא תדרוס את הטוקן התקין בטוקן
    מת — והמשתמש ינותק בביקור הבא בלי שעשה דבר.

    הביטול עצמו נעשה ב-after_request ולא כאן, וזה לא עניין של סגנון:
    Flask כותב את העוגייה כש-session מסומן permanent או modified, וכל
    כתיבה ל-session בתוך ה-view (למשל recurring_synced בדשבורד) הייתה
    מחזירה את modified לדלוק. גרוע מכך, ביטול permanent מוקדם היה הופך
    את העוגייה שתיכתב לעוגיית-דפדפן שנמחקת בסגירה — כלומר בדיוק הניתוק
    שאנחנו מונעים. ב-after_request כבר לא ירוץ קוד של view."""
    g.sf_skip_session_cookie = True


@app.after_request
def _honour_session_cookie_freeze(response):
    """מקפיא את כתיבת העוגייה — אלא אם ה-session רוקן במכוון.

    התנאי על user_id הוא לא פרט טכני. ההקפאה קיימת כדי לא לדרוס טוקן
    תקין בטוקן מת כשרענון נכשל, וזה רלוונטי רק כל עוד יש התחברות. אבל
    ‎session.clear()‎ — ביציאה יזומה, במחיקת חשבון, ובניתוק אחרי טוקן
    שנדחה — הוא בדיוק הרגע שבו העוגייה **חייבת** להיכתב, כדי שתימחק.

    בלי התנאי הזה מי שלחץ "התנתק" בדיוק כשהרענון נכשל קיבל הודעה שיצא,
    את עוגיות המכשיר נמחקות — ונשאר מחובר לגמרי, כי עוגיית ה-session
    שלו מעולם לא נגעה. הבקשה הבאה הייתה מחזירה אותו לאפליקציה."""
    if g.get("sf_skip_session_cookie") and session.get("user_id"):
        # שני אלה יחד הם מה ש-should_set_cookie של Flask בודק. הערכים
        # שבעוגייה אצל הדפדפן נשארים כפי שהם.
        session.permanent = False
        session.modified  = False
    return response


def _end_session(reason: str):
    """מסיים את ההתחברות ומשאיר עקבות.

    ניתוק היה עד עכשיו שקט לגמרי, ולכן משתמש שהתלונן שהוא "נזרק החוצה"
    לא הותיר שום דבר לחקור אותו. ההבטחה היא להישאר מחובר עד יציאה יזומה,
    אז כל ניתוק אחר הוא אירוע שצריך להיות אפשר לראות."""
    # warning ולא info: ההבטחה היא להישאר מחובר עד יציאה יזומה, אז כל
    # ניתוק אחר הוא אירוע שצריך להיות אפשר לראות
    logger.warning("session ended: %s", reason)
    if _sentry_dsn:
        sentry_sdk.capture_message(f"session ended: {reason}", level="warning")
    session.clear()


@app.before_request
def inject_auth():
    token = session.get("access_token")
    if not token:
        return

    # Supabase JWTs expire after ~1 hour; refresh ahead of expiry so a
    # long-lived Flask session keeps working without re-login.
    expires_at = session.get("token_expires_at") or 0
    if session.get("refresh_token") and time.time() > expires_at - 120:
        response, err, fatal = db.refresh_session(session["refresh_token"])
        if not err and response and response.session:
            token = response.session.access_token
            session["access_token"]     = token
            session["refresh_token"]    = response.session.refresh_token
            session["token_expires_at"] = response.session.expires_at
            session.permanent = True     # כל שימוש מאריך את חלון העוגייה
        elif fatal and time.time() >= expires_at:
            # הטוקן נדחה וגם טוקן הגישה כבר פג — ההתחברות מתה באמת ואין
            # מה לשחזר. רק כאן מנתקים.
            _end_session(f"refresh token rejected: {err}")
            return
        else:
            # לא מנתקים. שתי סיבות שונות מגיעות לכאן, ושתיהן בנות-שחזור:
            # תקלה זמנית (רשת, 5xx), או דחייה בזמן שטוקן הגישה עדיין בתוקף —
            # שזה בדיוק מה שקורה כשבקשה מקבילה כבר סובבה את הטוקן לפנינו.
            # הבקשה הזאת ממשיכה עם טוקן הגישה הקיים, והבאה תנסה שוב; אם
            # הדחייה אמיתית, הניתוק יקרה מעצמו כשטוקן הגישה יפוג.
            logger.warning("token refresh failed, keeping session: %s", err)
            _do_not_rewrite_session_cookie()

    db.set_auth_token(token)


# ─── זיכרון המכשיר ────────────────────────────────────────────────────────────
#
# דף הנחיתה הוא דף שיווק: הוא נועד למי שלא מכיר את SmartFin. מי שכבר התחבר
# מהמכשיר הזה פעם אחת לא צריך לראות אותו שוב — גם לא כשה-session נגמר או
# כשיצא ביוזמתו. שתי העוגיות כאן הן הזיכרון היחיד ששורד סיום session, ולכן
# הן נפרדות מעוגיית ה-session ומכילות רק את המינימום:
#
#   sf_returning — "כבר התחברת מכאן". קובע לאן הולך השורש.
#   sf_last_id   — המזהה שאיתו התחבר (אימייל או טלפון), כדי למלא מראש את
#                  הטופס. נמחקת ביציאה יזומה: מי שיצא במכוון ביקש שיפסיקו
#                  לזכור אותו, וגם ייתכן שהוא מפנה את המכשיר לבן משפחה אחר.
#
# שתיהן HttpOnly — אין להן שום שימוש ב-JS, וכך גם XSS לא יכול לקרוא את
# האימייל. אף החלטת הרשאה לא נשענת עליהן: ערך מזויף בהן משנה לכל היותר
# איזה דף מוגש למי שלא מחובר, ומה מודפס בשדה טקסט. הסיסמה עדיין נדרשת.
_DEVICE_COOKIE   = "sf_returning"
_LAST_ID_COOKIE  = "sf_last_id"
_DEVICE_COOKIE_MAX_AGE = 10 * 365 * 24 * 60 * 60   # עשר שנים, כמו ה-session


def _remember_device(response, identifier: str = ""):
    """מסמן את המכשיר כמוכר, ואם נמסר מזהה — זוכר גם אותו."""
    common = dict(max_age=_DEVICE_COOKIE_MAX_AGE, httponly=True,
                  samesite="Lax", secure=not _IS_DEV)
    response.set_cookie(_DEVICE_COOKIE, "1", **common)
    identifier = (identifier or "").strip()
    if identifier:
        # תקרה וניקוי תווי בקרה — הערך חוזר לדפדפן ונכנס לשדה טופס, ואין
        # שום סיבה שיהיה ארוך או מוזר. Jinja כבר עושה escaping בתבנית.
        safe = re.sub(r"[\x00-\x1f\x7f]", "", identifier)[:120]
        response.set_cookie(_LAST_ID_COOKIE, safe, **common)
    return response


def _remembered_identifier() -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", request.cookies.get(_LAST_ID_COOKIE, ""))[:120]


def _device_is_known() -> bool:
    return request.cookies.get(_DEVICE_COOKIE) == "1"


def _is_api_request() -> bool:
    """האם הבקשה מצפה ל-JSON ולא לעמוד HTML.

    ההפרדה הזאת היא מה שמבדיל בין "המשתמש ניווט לכתובת" לבין "הקוד בדף
    קרא לשרת". fetch עוקב אחרי הפניות בשקט, כך שדף HTML שמוחזר לקריאת
    API חוזר כתשובה תקינה עם קוד 200 — והלקוח מנסה לפרסר אותו כ-JSON
    ונכשל. המשתמש רואה "שגיאת רשת" שלא תיפסק לעולם."""
    return request.path.startswith("/api/")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            # קריאת API מקבלת 401 שהלקוח יודע לזהות; ניווט רגיל מקבל
            # הפניה לטופס ההתחברות כמו תמיד.
            if _is_api_request():
                return jsonify({"error": "ההתחברות הסתיימה — יש להתחבר מחדש"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    return {
        "id":             session.get("user_id"),
        "name":           session.get("user_name", "משתמש"),
        "family_id":      session.get("family_id"),
        "avatar_initial": session.get("avatar_initial", "מ"),
    }


def family_settings():
    """העדפות המשפחה המחוברת — נשלף פעם אחת לבקשה (cache על flask.g)."""
    if "family_settings" not in g:
        fid = session.get("family_id")
        g.family_settings = db.get_family_settings(fid) if fid else dict(db.DEFAULT_FAMILY_SETTINGS)
    return g.family_settings


@app.context_processor
def inject_family_settings():
    """family_settings זמין בכל תבנית (התגיות, המודאל וקבוצת ההעדפות תלויים בו).

    זה רץ לפני **כל** render_template, כולל error.html. לכן כאן, ורק כאן,
    כישלון שליפה לא מתפשט: אחרת תקלה במסד הייתה מפילה גם את דף השגיאה
    שנועד לדווח עליה, והמשתמש היה מקבל מסך ריק לגמרי. התבניות כבר יודעות
    להתמודד עם None — זה המצב של מי שלא מחובר.

    זו הקלה בתצוגה בלבד. החלטות שנשענות על ההעדפות — למשל שיוך עסקה לבן
    משפחה ב-_resolve_owner — קוראות ל-family_settings() ישירות וממשיכות
    להיכשל בגלוי, כי שם ערך שגוי נכתב למסד."""
    if "user_id" not in session:
        return {"family_settings": None}
    try:
        return {"family_settings": family_settings()}
    except db.DataUnavailable:
        return {"family_settings": None}


def _member_colors(family_id):
    """צבע קבוע לכל בן משפחה לפי סדר ההצטרפות (0=זהב, 1=ירקרק, 2=סגול, 3=כחול).
    משמש לתגי השם הצבעוניים על עסקאות."""
    if not family_id:
        return {}
    members = db.get_family_members(family_id)
    return {m["id"]: i % len(_OWNER_HEX) for i, m in enumerate(members)}


def _run_queries(tasks: dict) -> dict:
    """מריץ קבוצת שליפות DB ומחזיר {name: result}.
    היה בעבר מקבילי (ThreadPoolExecutor) אבל הלקוח של Supabase הוא singleton
    עם httpx client משותף — קריאות מקביליות מ-threads על אותו client גרמו ל-
    "Server disconnected" תחת gunicorn (השליפה נכשלה בשקט והחזירה אפסים). מאז
    שהעברנו את השרת ל-EU (אזור europe-west4) כל שליפה עולה ~30ms, אז הרצה
    רצופה מהירה לגמרי (~7 שליפות = ~0.2ש') ובטוחה. רץ ב-thread הראשי, אז גם
    flask.g/_request_cache עובד כרגיל."""
    return {name: fn() for name, fn in tasks.items()}


def _prime_request_cache(family_id, settings=None, categories=None, members=None, family=None):
    """מזריק ל-cache של הבקשה (flask.g) ערכים שכבר נשלפו במקביל, כדי
    ש-context-processors ו-_member_colors ישתמשו בהם במקום לשלוף שוב באותה
    בקשה. המפתחות חייבים להיות זהים לאלה שב-_request_cache ב-supabase_config."""
    cache = getattr(g, "_sf_cache", None)
    if cache is None:
        cache = g._sf_cache = {}
    if categories is not None:
        cache[f"categories:{family_id}"] = categories
    if members is not None:
        cache[f"members:{family_id}"] = members
    if family is not None:
        cache[f"family:{family_id}"] = family
    if settings is not None:
        g.family_settings = settings


# צבעי-מילוי מוצקים לעמודות גרף "לפי בן משפחה" — זהים לצבעי תגי-השם
# (.owner-0..5 ב-style.css, חייב להישאר מסונכרן; מספר הצבעים כאן קובע כמה
# בני משפחה מקבלים צבע ייחודי לפני שהמערכת חוזרת מהתחלה). משותפת (ללא
# user_id) מקבלת אפור כמו .owner-shared. צבעים לא-שגרתיים שלא מתנגשים
# עם הסמנטיים (ירוק=הכנסה, אדום=הוצאה, זהב=חיסכון).
_OWNER_HEX  = {
    0: "#2E67A8",  # כחול (מתן)
    1: "#7048B0",  # סגול (אור)
    2: "#A0457C",  # שזיף-מג'נטה
    3: "#A85C3E",  # טרקוטה
    4: "#5E7391",  # כחול-אפור צפחה
    5: "#8A6A52",  # חום-טאופ
}
_SHARED_HEX = "#78716C"


# ─── Auth routes ──────────────────────────────────────────────────────────────

# ─── בדיקת כתובת מייל ─────────────────────────────────────────────────────────
#
# לא RFC מלא — בדיוק מה שמונע את הטעות שקרתה בפועל: כתובת בלי סיומת.
# לשני הטפסים יש ‎novalidate‎ (בכוונה, כדי שהשגיאות יהיו בעברית ובעיצוב
# שלנו ולא בועית דפדפן באנגלית), ובשרת לא נבדק כלום — אז ‎israel@gmial‎
# או ‎israel@gmail‎ נרשמו בהצלחה.
#
# למה זה חמור יותר משנשמע: המשתמש לא מגלה כלום ברגע ההרשמה. הוא מגלה
# חודש אחר כך, כשהוא מנסה לאפס סיסמה והקישור נשלח לכתובת שלא קיימת.
# אין לו מוצא, ואין שום מסלול באפליקציה לתקן כתובת. במסד יש כבר חשבון
# כזה מיולי.
#
# 254 תווים הוא האורך המרבי של כתובת מייל לפי התקן.
_EMAIL_RE = re.compile(r"^[^@\s]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")


def _looks_like_email(value: str) -> bool:
    value = (value or "").strip()
    return len(value) <= 254 and bool(_EMAIL_RE.match(value))


def _login_error(err: str) -> str:
    """ממפה כשל התחברות להודעה שאומרת מה קרה.

    כל כשל הוצג כ"אימייל/טלפון או סיסמה שגויים" — גם כשהסיסמה נכונה
    לגמרי. ‎db.sign_in‎ תופסת כל חריגה ומחזירה את הטקסט שלה, אז הגבלת
    קצב של Supabase, מייל שלא אומת ותקלת חיבור כולם נראו זהים.

    המקרה שהופך את זה מאי-נוחות למלכודת: אם אימות מייל יופעל אי-פעם
    בפרויקט, **כל משתמש חדש ננעל לצמיתות** — הוא נרשם, מקבל "כעת ניתן
    להתחבר", ומקבל "סיסמה שגויה" לנצח. גם "שכחתי סיסמה" לא יעזור, כי
    הסיסמה מעולם לא הייתה הבעיה.

    צד ההרשמה ממפה חמש שגיאות שונות בקפידה; כאן היה אפס."""
    text = (err or "").lower()
    if "email not confirmed" in text or "not confirmed" in text:
        return ("החשבון עדיין לא אומת. בדקו את תיבת המייל — נשלח אליכם "
                "קישור אישור, וייתכן שהוא בספאם.")
    if "rate limit" in text or "too many" in text:
        return "יותר מדי ניסיונות בזמן קצר — נסו שוב בעוד כמה דקות"
    if "not configured" in text or "connection" in text or "timeout" in text:
        return "השירות אינו זמין כרגע — נסו שוב בעוד רגע"
    return "אימייל/טלפון או סיסמה שגויים"


def _signup_form():
    """השדות שהוקלדו בטופס ההרשמה, כדי להחזיר אותם עם השגיאה.
    בלי הסיסמאות — אין סיבה שהן ישבו ב-HTML של תשובה."""
    return {
        "first_name":  request.form.get("first_name", "").strip(),
        "last_name":   request.form.get("last_name", "").strip(),
        "email":       request.form.get("email", "").strip(),
        "phone":       request.form.get("phone", "").strip(),
        "invite_code": request.form.get("invite_code", "").strip(),
    }


def _normalize_phone(raw: str) -> str:
    """מנרמל מספר טלפון להשוואה/שמירה עקבית: ספרות בלבד, בצורה המקומית.

    קידומת ‎+972‎ מומרת ל-‎0‎. בלי זה אותו מספר בדיוק נשמר בשתי צורות:
    מי שנרשם עם ‎+972-54-1234567‎ נשמר כ-‎972541234567‎, ואז ההתחברות
    שלו עם ‎054-1234567‎ לא מוצאת אותו לעולם — ושני אנשים יכלו "לתפוס"
    את אותו מספר, כל אחד בכתיב אחר.
    """
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    return digits


# מספר טלפון ישראלי: נייד (‎05X‎ ועוד שבע ספרות), קווי (‎0X‎ ועוד שבע),
# או ‎07X‎ ועוד שבע. הבדיקה קיימת מאותה סיבה כמו זו של המייל — הטפסים
# הם ‎novalidate‎ ובשרת לא נבדק דבר, אז ‎1‎ היה מספר תקין: הוא נשמר, הפך
# למזהה התחברות חלופי חסר משמעות, ובגלל האינדקס הייחודי על הטלפון הוא
# גם חסם את הערך הזה לכל שאר המשתמשים לתמיד.
_PHONE_RE = re.compile(r"^0(5\d|7\d|[2-4689])\d{7}$")


def _looks_like_phone(normalized: str) -> bool:
    return bool(_PHONE_RE.match(normalized or ""))


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    error = None
    # מה ימלא את שדה "אימייל או טלפון". ב-GET זה המזהה שנשמר מההתחברות
    # הקודמת מהמכשיר הזה; אחרי ניסיון כושל זה מה שהמשתמש הקליד עכשיו,
    # כדי שלא יצטרך להקליד שוב אחרי טעות בסיסמה.
    identifier = _remembered_identifier()
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password   = request.form.get("password", "")

        if "@" in identifier:
            email = identifier
        else:
            email = db.get_email_by_phone(_normalize_phone(identifier))

        response, err = db.sign_in(email, password) if email else (None, "not found")
        if err:
            error = _login_error(err)
        else:
            user = response.user
            # Set JWT before querying profiles (RLS requires auth.uid())
            db.set_auth_token(response.session.access_token)
            db.log_login_event()  # תיעוד כניסה פנימי (לבעל האתר)
            profile, profile_ok = db.fetch_profile(user.id)

        if not err and not profile_ok:
            # הסיסמה נכונה, אבל הפרופיל לא נקרא. לא נכנסים: המשך מכאן היה
            # מתחיל session בלי family_id, ומשם ensure_family היה יוצר
            # משפחה חדשה ודורס את השיוך הקיים — ניתוק לצמיתות מכל
            # ההיסטוריה בגלל תקלה של שתי שניות. כישלון שאפשר לנסות שוב
            # אחריו הוא התוצאה הנכונה.
            error = "לא הצלחנו לטעון את הפרטים שלך — נסה שוב בעוד רגע"

        elif not err:
            session.permanent = True  # stay signed in until explicit logout
            session["user_id"]          = user.id
            session["user_email"]       = user.email
            session["access_token"]     = response.session.access_token
            session["refresh_token"]    = response.session.refresh_token
            session["token_expires_at"] = response.session.expires_at
            session["user_name"]      = db.first_name(profile.get("name", "משתמש")) if profile else "משתמש"
            session["avatar_initial"] = (profile.get("avatar_initial") or "מ") if profile else "מ"
            session["family_id"]      = profile.get("family_id") if profile else None

            # Auto-create family if user doesn't have one
            if not session["family_id"]:
                session["family_id"] = db.ensure_family(user.id)

            if not session["family_id"]:
                # גם היצירה נכשלה. session בלי משפחה הוא אפליקציה שאי אפשר
                # לעשות בה כלום, ובניסיון הבא הוא ינסה ליצור משפחה שוב —
                # אז עדיף לא להיכנס מאשר להיכנס למצב תקוע.
                session.clear()
                error = "לא הצלחנו לטעון את הפרטים שלך — נסה שוב בעוד רגע"

            else:
                # מכאן והלאה המכשיר מוכר: גם אם ה-session ייגמר יום אחד,
                # השורש יביא אותו לטופס ההתחברות ולא חזרה לדף השיווק.
                return _remember_device(redirect(url_for("dashboard")), identifier)

    # העמוד נושא עכשיו את המזהה שנשמר, כך שהוא תלוי-עוגייה בדיוק כמו השורש
    # ואסור שיישמר במטמון של דפדפן או proxy.
    response = make_response(render_template("login.html", error=error,
                                             active_tab="login",
                                             remembered_identifier=identifier))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"
    return response


@app.route("/signup", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def signup():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        first_name       = request.form.get("first_name", "").strip()
        last_name        = request.form.get("last_name", "").strip()
        email            = request.form.get("email", "").strip()
        phone            = _normalize_phone(request.form.get("phone", ""))
        password         = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        invite_code      = request.form.get("invite_code", "").strip()

        if not first_name or not last_name or not email or not password or not phone:
            error = "נא למלא את כל השדות"
        elif not _looks_like_email(email):
            error = "כתובת המייל אינה תקינה — בדקו שהיא מלאה, למשל israel@gmail.com"
        elif not _looks_like_phone(phone):
            error = "מספר הטלפון אינו תקין — למשל 050-1234567"
        elif len(password) < 6:
            error = "הסיסמה חייבת להכיל לפחות 6 תווים"
        elif password != password_confirm:
            error = "הסיסמאות אינן תואמות"
        else:
            name = f"{first_name} {last_name}"
            response, err = db.sign_up(email, password, name, phone)
            if err:
                # ממפים שגיאות מוכרות מ-Supabase להודעה בעברית — בעבר כל
                # שגיאה (גם הגבלת קצב, פורמט לא תקין וכו') הוצגה תמיד כ"האימייל
                # כבר קיים" בטעות, מה שהטעה כשהבעיה האמיתית הייתה שונה לגמרי
                err_lower = err.lower()
                if "already registered" in err_lower or "already exists" in err_lower:
                    error = "הרשמה נכשלה – האימייל כבר קיים"
                elif ("duplicate" in err_lower and "phone" in err_lower) or "database error saving new user" in err_lower:
                    # שגיאה זו מגיעה מ-trigger שנכשל על האינדקס הייחודי של טלפון
                    # ב-DB — ה-Auth API של Supabase לא חושף את פרטי הקונפליקט,
                    # רק הודעה גנרית. זו כרגע העילה היחידה שגורמת ל-trigger להיכשל.
                    error = "הרשמה נכשלה – מספר הטלפון כבר רשום למשתמש אחר"
                elif "invalid" in err_lower and "email" in err_lower:
                    error = "הרשמה נכשלה – כתובת המייל אינה תקינה, בדוק שהזנת אותה נכון"
                elif "rate limit" in err_lower:
                    error = "יותר מדי ניסיונות הרשמה בזמן קצר — נסה שוב בעוד כמה דקות"
                else:
                    # לא מדליפים את השגיאה הפנימית למשתמש — רק ללוג השרת
                    logger.error("signup: %s", err)
                    error = "הרשמה נכשלה — נסה שוב בעוד כמה רגעים"
            else:
                # הצטרפות למשפחה קיימת לפי קוד ההזמנה. כישלון כאן לא מבטל את
                # ההרשמה — המשתמש כבר נוצר ב-Auth ואסור להשאיר אותו בלי דרך
                # להיכנס — אבל הוא כן חייב להיאמר בקול. בעבר הערך המוחזר נזרק,
                # וכל מצטרף קיבל "נרשמת בהצלחה" ואז משפחה חדשה משלו בשקט.
                success = "נרשמת בהצלחה! כעת ניתן להתחבר."
                if invite_code and response and response.user:
                    # ה-RPC מזהה את המצטרף דרך auth.uid(), ולכן ה-client חייב
                    # לשאת את הטוקן של המשתמש החדש. לא מסתמכים על כך שה-SDK
                    # יעשה זאת לבד אחרי sign_up — קובעים אותו במפורש, כמו
                    # בכל מסלול אחר באפליקציה.
                    session_obj = getattr(response, "session", None)
                    if session_obj and session_obj.access_token:
                        db.set_auth_token(session_obj.access_token)
                    _, join_err = db.join_family_by_code(invite_code)
                    if join_err:
                        logger.warning("signup join failed for %s: %s", email, join_err)
                        success = (f"נרשמת בהצלחה! אבל {join_err}. "
                                   "אפשר להתחבר ולהצטרף למשפחה דרך ההגדרות.")
                # ההרשמה לא מחברת אוטומטית, אבל היא כן הופכת את המכשיר
                # למוכר — מי שהרגע פתח חשבון בוודאי לא צריך לראות שוב את
                # דף השיווק, והמייל שלו כבר ממולא בטופס.
                return _remember_device(
                    make_response(render_template("login.html", active_tab="login",
                                                  success=success,
                                                  remembered_identifier=email)),
                    email)

    # מה שהוקלד חוזר עם השגיאה.
    #
    # עד היום כל שגיאת הרשמה — מייל לא תקין, סיסמאות שלא תואמות, מייל
    # שכבר קיים — מחקה את כל ששת השדות, **כולל קוד ההזמנה**. מי שקיבל
    # קוד בוואטסאפ והקליד סיסמה קצרה מדי נשאר בלי הקוד ובלי הפרטים,
    # וצריך לחזור לשיחה ולחפש. זה ההפך הגמור מצד ההתחברות, ששומר את
    # המזהה במפורש "כדי שלא יצטרך להקליד שוב אחרי טעות בסיסמה".
    #
    # הסיסמאות לא חוזרות, במכוון: אין סיבה שסיסמה תשב ב-HTML של תשובה.
    return render_template("login.html", error=error, active_tab="signup",
                           signup=_signup_form()), 422 if error else 200


@app.route("/logout", methods=["POST", "GET"])
def logout():
    """יציאה יזומה מחזירה לדף הנחיתה, ומוחקת את כל מה שנשמר על המכשיר.

    זו הנקודה שבה כל הזיכרון מתאפס — לא רק ה-session אלא גם שתי עוגיות
    המכשיר. הכוונה מדויקת: יציאה יזומה היא הדרך היחידה החוצה, ומי שבחר
    בה מקבל בדיוק את מה שאורח מקבל — דף הנחיתה, ומשם כפתור "התחברות".
    זה גם מה שהופך את סימון המכשיר לאמין: מכאן והלאה, מכשיר שמסומן מוכר
    אבל אין לו session הוא בהכרח מקרה שבו ההתחברות נגמרה מעצמה — וזה
    בדיוק המקרה שבו דף שיווק הוא התשובה הלא נכונה."""
    session.clear()
    response = redirect(url_for("dashboard"))
    response.delete_cookie(_LAST_ID_COOKIE, samesite="Lax", secure=not _IS_DEV)
    response.delete_cookie(_DEVICE_COOKIE,  samesite="Lax", secure=not _IS_DEV)
    return response


@app.route("/api/auth/forgot", methods=["POST"])
@limiter.limit("3 per minute")
def forgot_password():
    body  = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip()
    if not email:
        return jsonify({"error": "נא להזין אימייל"}), 422
    # פורמט פסול הוא לא מידע על מי רשום, ולכן מותר לומר אותו בקול —
    # בניגוד לתשובה שלמטה, שתמיד "נשלח" כדי לא לחשוף אילו כתובות קיימות.
    # בלי זה מי שהקליד כתובת שבורה קיבל "נשלח קישור" וחיכה לו לשווא.
    if not _looks_like_email(email):
        return jsonify({"error": "כתובת המייל אינה תקינה"}), 422

    redirect_to = request.host_url.rstrip("/") + url_for("reset_password")
    db.send_reset_email(email, redirect_to)
    # תמיד מחזירים הצלחה — לא חושפים אילו אימיילים רשומים
    return jsonify({"status": "ok"})


@app.route("/reset-password")
def reset_password():
    """עמוד קביעת סיסמה חדשה — הטוקן מגיע ב-fragment של הקישור מהמייל."""
    return render_template("reset_password.html")


@app.route("/api/auth/reset", methods=["POST"])
# לא מאומת, ומקבל טוקן שחזור מגוף הבקשה — כלומר פתוח לניחוש טוקנים.
# ‎/api/auth/forgot‎ שלצידו כבר מוגבל ל-3 לדקה; זה נשכח.
@limiter.limit("5 per minute")
def reset_password_submit():
    body             = request.get_json(silent=True) or {}
    access_token     = body.get("access_token", "")
    password         = body.get("password", "")
    password_confirm = body.get("password_confirm", "")

    if not access_token:
        return jsonify({"error": "קישור האיפוס לא תקין או שפג תוקפו"}), 400
    if len(password) < 6:
        return jsonify({"error": "הסיסמה חייבת להכיל לפחות 6 תווים"}), 422
    if password != password_confirm:
        return jsonify({"error": "הסיסמאות אינן תואמות"}), 422

    ok, err = db.update_password(access_token, password)
    if not ok:
        logger.error("reset password: %s", err)
        return jsonify({"error": "האיפוס נכשל — נסה לבקש קישור חדש"}), 400
    return jsonify({"status": "ok"})


# ─── Onboarding (משפחה חדשה בלבד) ──────────────────────────────────────────────

# סט התחלתי גנרי — כל משפחה חדשה יכולה לערוך, למחוק או להוסיף עליו.
# (לא כולל שמות ספציפיים כמו "קופת גמל אנליסט" שרלוונטיים רק למשפחה מסוימת)
_DEFAULT_CATEGORIES = [
    {"name": "משכורת",          "icon": "💼", "type": "income"},
    {"name": "הכנסה נוספת",     "icon": "💵", "type": "income"},
    {"name": "דיור ושכירות",    "icon": "🏠", "type": "expense"},
    {"name": "חשבונות",         "icon": "💡", "type": "expense"},
    {"name": "סופר ומזון",      "icon": "🛒", "type": "expense"},
    {"name": "רכב ותחבורה",     "icon": "🚗", "type": "expense"},
    {"name": "ביגוד וטיפוח",    "icon": "👗", "type": "expense"},
    {"name": "בריאות",          "icon": "🏥", "type": "expense"},
    {"name": "מסעדות ובילויים", "icon": "🍽️", "type": "expense"},
    {"name": "חופשות",          "icon": "✈️", "type": "expense"},
    {"name": "שופינג",          "icon": "🛍️", "type": "expense"},
    {"name": "מנויים",          "icon": "📺", "type": "expense"},
    {"name": "אחר",             "icon": "📦", "type": "expense"},
    {"name": "חיסכון כללי",     "icon": "💰", "type": "savings"},
    {"name": "קרן השתלמות",     "icon": "🏦", "type": "savings"},
    {"name": "פיקדון בנקאי",    "icon": "📈", "type": "savings"},
]


@app.route("/onboarding")
@login_required
def onboarding():
    user = get_current_user()
    if not user["family_id"] or not db.family_needs_onboarding(user["family_id"]):
        return redirect(url_for("dashboard"))

    family = db.get_family(user["family_id"])
    return render_template(
        "onboarding.html",
        user=user,
        family=family,
        default_categories=_DEFAULT_CATEGORIES,
    )


@app.route("/api/onboarding/complete", methods=["POST"])
@login_required
def onboarding_complete():
    user = get_current_user()
    if not user["family_id"]:
        return jsonify({"error": "לא מצאנו את המשפחה שלך — רעננו את הדף, ואם זה חוזר התחברו מחדש"}), 400
    if not db.family_needs_onboarding(user["family_id"]):
        return jsonify({"error": "ההגדרה הראשונית כבר הושלמה"}), 400

    body = request.get_json(silent=True) or {}
    family_name = (body.get("family_name") or "").strip()
    categories  = body.get("categories") or []

    if not categories:
        return jsonify({"error": "נא לבחור לפחות קטגוריה אחת"}), 422

    if family_name:
        db.update_family_name(user["family_id"], family_name)

    # שלב "איך תרצו לעקוב?" — שיוך עסקאות לבני משפחה לפי בחירת המשפחה
    if isinstance(body.get("owner_attribution"), dict):
        oa = body["owner_attribution"]
        db.update_family_settings(user["family_id"], {"owner_attribution": {
            k: bool(oa.get(k, False)) for k in ("expense", "income", "savings")
        }})

    count, err = db.bulk_add_categories(user["family_id"], categories)
    if err:
        logger.error("onboarding bulk_add_categories: %s", err)
        return jsonify({"error": "שמירת הקטגוריות נכשלה — נסה שוב"}), 500

    return jsonify({"status": "ok", "categories_created": count})


def _sync_recurring(family_id):
    """משלים מופעים של עסקאות קבועות, פעם ביום לכל משתמש.

    שני דברים תוקנו כאן ביחד.

    ראשית, זה רץ רק מהדשבורד. מי שהגיע ישר לעמוד החודש — מסימנייה,
    מהתפריט התחתון או מקישור — ראה חודש בלי המשכורת ובלי ההוראות
    הקבועות, ולא היה שום דבר שיסביר לו למה. המספרים תוקנו רק אם במקרה
    עבר דרך דף הבית.

    שנית, הסימון "סונכרן להיום" נכתב גם כשהיצירה נכשלה — ואז הניסיון
    הבא רק למחרת. כשל שנראה כהצלחה משאיר חודש שלם חסר.

    מסומן רק אחרי הצלחה, כך שכישלון חולף נפתר בטעינת העמוד הבאה."""
    if not family_id:
        return
    today_str = clock.today().isoformat()
    if session.get("recurring_synced") == today_str:
        return
    _, ok = db.materialize_recurring(family_id)
    if ok:
        session["recurring_synced"] = today_str


# ─── Main pages (5 עמודים: בית · החודש · השוואה · פרויקטים · הגדרות) ────────

@app.route("/")
def dashboard():
    """השורש מגיש שני דברים שונים: דף נחיתה ציבורי למי שלא מחובר, והדשבורד
    למי שכן.

    עד היום הוא היה מוגן ב-login_required והפנה ישר ל-/login, כך שכל מי
    שקיבל קישור נחת על טופס התחברות בלי לדעת מה זה ולמה שימסור נתונים
    פיננסיים. שם הפונקציה נשאר dashboard כדי שכל url_for הקיים ימשיך לעבוד.

    מי שלא מחובר מקבל אחד משניים: מכשיר שמעולם לא התחבר מכאן רואה את דף
    הנחיתה, ומכשיר מוכר מדלג עליו ישר לטופס ההתחברות. דף שיווק הוא התשובה
    הנכונה לאורח, ולא למי שרק רצה להיכנס לתקציב שלו. ‎?intro=1 הוא הדרך
    לראות את דף הנחיתה בכל זאת — משם מגיע כפתור "חזרה" שבדף ההתחברות."""
    if "user_id" not in session:
        if _device_is_known() and not request.args.get("intro"):
            response = redirect(url_for("login"))
        else:
            response = make_response(render_template("landing.html"))
        # התוכן כאן תלוי במצב ההתחברות ובעוגיית המכשיר, ולכן אסור שיישמר
        # במטמון כלשהו — ו-Vary אומר את זה גם ל-proxy שבדרך.
        response.headers["Cache-Control"] = "no-store"
        response.headers["Vary"] = "Cookie"
        return response

    user      = get_current_user()
    now       = clock.now()
    family_id = user["family_id"]

    if not family_id:
        return render_template(
            "index.html", active_page="dashboard", user=user,
            summary=db._empty_summary(), transactions=[], categories=db.get_categories(None),
            member_colors={}, month_label=_month_label(now.year, now.month),
            year=now.year, month=now.month, is_new_family=True,
        )

    # עלול לכתוב שורות, אז לפני מקבץ השליפות
    _sync_recurring(family_id)

    # שליפות בלתי-תלויות במקביל — מכווץ ~5 קריאות רצופות ל-Supabase לזמן של ~1
    batch = _run_queries({
        "settings":   lambda: db.get_family_settings(family_id),
        "summary":    lambda: db.get_monthly_summary(family_id, now.year, now.month),
        "categories": lambda: db.get_categories(family_id),
        "members":    lambda: db.get_family_members(family_id),
        "is_new":     lambda: db.family_has_no_transactions(family_id),
    })

    # "צריך onboarding" == אפס קטגוריות — נגזר מהקטגוריות שכבר שלפנו (בלי שליפה נוספת)
    if not batch["categories"]:
        return redirect(url_for("onboarding"))

    # "עסקאות אחרונות" תלויות בהעדפות — נשלפות אחרי שיש לנו אותן
    transactions = db.get_recent_transactions(family_id, settings=batch["settings"], viewer_user_id=user["id"])

    # מיחזור תוצאות המקבץ ל-context-processors ו-_member_colors (בלי שליפה חוזרת)
    _prime_request_cache(family_id, settings=batch["settings"], categories=batch["categories"], members=batch["members"])

    return render_template(
        "index.html",
        active_page="dashboard",
        user=user,
        summary=batch["summary"],
        transactions=transactions,
        categories=batch["categories"],
        member_colors=_member_colors(family_id),
        month_label=_month_label(now.year, now.month),
        year=now.year,
        month=now.month,
        is_new_family=batch["is_new"],
    )


@app.route("/month")
@login_required
def month_view():
    """עמוד החודש: כל הנתונים והגרפים של חודש נתון (ברירת מחדל: הנוכחי)."""
    user      = get_current_user()
    now       = clock.now()
    # type=int מוודא שזה מספר, לא שזה חודש קיים: ?month=99999999 הפיל את
    # העמוד ב-500 עד שהתגלה. נופלים לחודש הנוכחי במקום להתפוצץ.
    year      = request.args.get("year",  now.year,  type=int)
    month     = request.args.get("month", now.month, type=int)
    if not 1 <= (month or 0) <= 12:
        month = now.month
    if not 1970 <= (year or 0) <= 2100:
        year = now.year
    family_id = user["family_id"]

    # לפני השליפות: בלי זה חודש שנפתח ישירות (סימנייה, תפריט, קישור)
    # מוצג בלי המשכורת ובלי ההוראות הקבועות
    _sync_recurring(family_id)

    is_current = (year == now.year and month == now.month)

    if not family_id:
        return render_template(
            "month.html", active_page="month", user=user,
            summary=db._empty_summary(), expense_breakdown=[], income_breakdown=[],
            savings_breakdown=[], member_breakdowns=[], anomalies=[], month_transactions=[],
            member_colors={}, month_label=_month_label(year, month), year=year, month=month,
            strip_months=[{"year": year, "month": month}], hebrew_months=_HEBREW_MONTHS,
            is_current=is_current, summary_data=db._empty_summary(),
            expense_data=[], members_data=[],
            # התבנית ניגשת ל-project_month ללא תנאי. המסלול הזה נשכח כשנוספו
            # הפרויקטים, ומשתמש בלי משפחה קיבל 500 במקום העמוד הריק המיועד.
            project_month={"expense": 0, "income": 0, "savings": 0, "transactions": []},
        )

    # שלב 1 — שליפות בלתי-תלויות. שורות החודש נשלפות **פעם אחת**, וכל
    # הסיכומים נגזרים מהן: הסיכום, שלושת הפילוחים לקטגוריה, שני הפילוחים
    # לבן משפחה ורשימת העסקאות היו שבע שאילתות על אותן שורות בדיוק.
    #
    # החיסכון בזמן (כ-180ms) הוא הצד הפחות חשוב. העיקר הוא שכל אחת מהשבע
    # גזרה לעצמה מחדש את אותם שני כללים — החרגת עסקאות פרויקט, והסתרת
    # פרויקט אישי של בן משפחה אחר — והכלל השני כבר נשכח פעם אחת (ראו
    # ההערה על התאמת קטגוריות לפי שם, למטה). עכשיו הוא מיושם פעם אחת.
    p1 = _run_queries({
        "settings":   partial(db.get_family_settings, family_id),
        "members":    partial(db.get_family_members, family_id),
        "categories": partial(db.get_categories, family_id),
        "rows":       partial(db.fetch_month_rows, family_id, year, month),
        # רצועת החודשים בראש העמוד — RPC אחד שמחזיר את כל החודשים עם נתונים
        "archive":    partial(db.get_months_archive, family_id),
    })
    settings_ = p1["settings"]
    rows      = p1["rows"]

    summary = db.summary_from_rows(rows)
    # תקציבי הקטגוריות נוספים לפילוח ההוצאות: הפס מודד מול ההחלטה של
    # המשפחה במקום מול סך ההוצאות החודש
    expense_breakdown = db.apply_budgets(
        db.category_breakdown_from_rows(rows, p1["categories"], "expense"), settings_)
    income_breakdown  = db.category_breakdown_from_rows(rows, p1["categories"], "income")
    savings_breakdown = db.category_breakdown_from_rows(rows, p1["categories"], "savings")

    # רצועת החודשים: מהישן לחדש (ה-RPC מחזיר מהחדש לישן), ותמיד כוללת את
    # החודש הנצפה — גם אם אין בו עסקאות ולכן הוא לא חוזר מה-RPC
    strip_months = [{"year": m["year"], "month": m["month"]} for m in reversed(p1["archive"] or [])]
    if not any(m["year"] == year and m["month"] == month for m in strip_months):
        strip_months.append({"year": year, "month": month})
        strip_months.sort(key=lambda m: (m["year"], m["month"]))

    # שלב 2 — שליפות שתלויות בהעדפות/בסיכום, גם הן במקביל
    active_types = [t for t in ("expense", "income", "savings") if settings_["owner_attribution"].get(t)]
    p2_tasks = {
        # קטגוריה עם תקציב מדלגת על התראת הממוצע — יש לה התראה מדויקת יותר
        "anomalies":    partial(db.get_anomalies, family_id, year, month, summary, settings_,
                                skip_categories=[r["name"] for r in expense_breakdown
                                                 if r.get("budget")]),
    }
    if is_current:
        p2_tasks["run_rate"] = partial(db.get_run_rate_forecasts, family_id, year, month, settings_)
        # רק לחודש הנוכחי: "ההוצאות הקבועות שלנו" הוא מספר של עכשיו,
        # ולחודש שעבר הוא היה משהו אחר שאין לנו דרך לשחזר
        p2_tasks["recurring"] = partial(db.get_recurring_transactions, family_id,
                                        settings=settings_)
    p2 = _run_queries(p2_tasks)

    anomalies = db.budget_alerts(expense_breakdown) + list(p2["anomalies"])
    fixed = None
    if is_current:
        anomalies += p2["run_rate"]
        fixed = db.summarise_recurring(p2["recurring"])
    month_transactions = db.month_transactions_from_rows(rows, settings_, user["id"])

    # פעילות פרויקטים החודש — מוחרגת מהמאזן/הגרפים, ומוצגת בנפרד. נגזרת
    # מהעסקאות שכבר נשלפו (שכוללות גם עסקאות פרויקט), בלי שליפה נוספת.
    project_txs = [t for t in month_transactions if t.get("project_id")]
    project_month = {
        "expense":      round(sum(t["amount"] for t in project_txs if t["type"] == "expense"), 2),
        "income":       round(sum(t["amount"] for t in project_txs if t["type"] == "income"), 2),
        "savings":      round(sum(t["amount"] for t in project_txs if t["type"] == "savings"), 2),
        "transactions": project_txs,
    }

    # ומכאן — רק העסקאות הרגילות. כל שאר נתוני החודש (סיכום, פילוח קטגוריות,
    # חלוקה בין בני משפחה, חריגות) כבר מסננים עסקאות פרויקט בשאילתה עצמה;
    # הרשימה הזו הייתה היחידה שלא, והתבנית מתאימה עסקאות לקטגוריות לפי *שם*.
    # קטגוריית פרויקט ששמה זהה לקטגוריה משפחתית (למשל "אחר", שנזרעת בשתיהן)
    # גרמה לעסקת הפרויקט להופיע בתוך הקטגוריה החודשית — בלי להיספר בסכום שלה.
    month_transactions = [t for t in month_transactions if not t.get("project_id")]

    # מיחזור המקבץ ל-context-processors ו-_member_colors (בלי שליפה חוזרת)
    _prime_request_cache(family_id, settings=settings_, members=p1["members"])

    # גרף חלוקה בין בני משפחה לכל סוג עסקה שהמשפחה הפעילה בו שיוך
    _type_labels = {"expense": "הוצאות", "income": "הכנסות", "savings": "חיסכון"}
    mcolors = _member_colors(family_id)
    member_breakdowns = []
    for t in active_types:
        # ‎mb‎ ולא ‎rows‎: ‎rows‎ הוא שורות החודש, ודריסה שלו כאן הייתה
        # מרעילה את כל מה שנגזר ממנו בהמשך
        mb = db.member_breakdown_from_rows(rows, t)
        for r in mb:
            idx = mcolors.get(r.get("user_id"))
            r["color"] = _OWNER_HEX.get(idx, _SHARED_HEX) if idx is not None else _SHARED_HEX
        if mb:
            member_breakdowns.append({"type": t, "label": _type_labels[t], "rows": mb})

    return render_template(
        "month.html",
        active_page="month",
        user=user,
        summary=summary,
        expense_breakdown=expense_breakdown,
        income_breakdown=income_breakdown,
        savings_breakdown=savings_breakdown,
        member_breakdowns=member_breakdowns,
        anomalies=anomalies,
        month_transactions=month_transactions,
        project_month=project_month,
        fixed=fixed,
        member_colors=_member_colors(family_id),
        month_label=_month_label(year, month),
        year=year,
        month=month,
        strip_months=strip_months,
        hebrew_months=_HEBREW_MONTHS,
        is_current=is_current,
        summary_data=summary,
        # רק קטגוריות פעילות (total>0) — כדי שאינדקסי הצבעים בגרף העגול
        # יתאמו למקרא (שגם הוא מסונן ל-active), ובלי פרוסות ברוחב 0.
        expense_data=[c for c in expense_breakdown if c.get("total", 0) > 0],
        members_data=member_breakdowns,
    )


@app.route("/month.csv")
@login_required
def month_csv():
    """ייצוא עסקאות החודש כ-CSV.

    נתונים שאפשר להוציא הם נתונים שאפשר לבטוח בהם, וזו התשובה הזולה
    ביותר ל"מה קורה אם ארצה לעזוב". גם כל שיחה עם רואה חשבון מתחילה כאן.

    שני פרטים שקובעים אם הקובץ באמת נפתח נכון בעברית:
    · BOM בתחילת הקובץ — בלעדיו אקסל מפרש UTF-8 כקידוד מקומי, וכל
      התיאורים והקטגוריות הופכים לג'יבריש. זו התלונה מספר אחת על ייצוא
      CSV בעברית, והיא נראית כמו באג באפליקציה ולא בתוכנה שפותחת.
    · ‎\r\n‎ כסוף שורה — מה ש-Excel מצפה לו."""
    user      = get_current_user()
    now       = clock.now()
    year      = request.args.get("year",  now.year,  type=int)
    month     = request.args.get("month", now.month, type=int)
    if not 1 <= (month or 0) <= 12:
        month = now.month
    if not 1970 <= (year or 0) <= 2100:
        year = now.year

    rows = []
    if user["family_id"]:
        # אותה שליפה שמזינה את עמוד החודש, כולל סינון פרויקט אישי של
        # בן משפחה אחר — הייצוא לא אמור לחשוף מה שהמסך מסתיר
        rows = db.get_month_transactions(
            user["family_id"], year, month,
            settings=family_settings(), viewer_user_id=user["id"])

    _TYPE_HE = {"expense": "הוצאה", "income": "הכנסה", "savings": "חיסכון"}

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(["תאריך", "סוג", "סכום", "קטגוריה", "תיאור",
                     "בן משפחה", "פרויקט", "עסקה קבועה"])
    for tx in rows:
        writer.writerow([
            tx["date"],
            _TYPE_HE.get(tx["type"], tx["type"]),
            f'{tx["amount"]:.2f}',
            tx.get("category_name") or "",
            tx.get("description") or "",
            tx.get("user_name") or "",
            tx.get("project_name") or "",
            "כן" if tx.get("is_recurring") or tx.get("recurring_parent_id") else "",
        ])

    response = make_response("\ufeff" + buffer.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="smartfin-{year}-{month:02d}.csv"')
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/months")
@login_required
def months():
    """עמוד השוואה: החודש הנוכחי מול חודשים קודמים + כניסה לכל חודש."""
    user      = get_current_user()
    family_id = user["family_id"]
    _sync_recurring(family_id)
    archive   = db.get_months_archive(family_id)              if family_id else []
    trend     = db.get_monthly_trend(family_id, num_months=12) if family_id else []
    now       = clock.now()
    return render_template("months.html", active_page="months", user=user,
                           archive=archive, trend_data=trend,
                           today_year=now.year, today_month=now.month,
                           _HEBREW_MONTHS=_HEBREW_MONTHS)


@app.route("/stats")
@login_required
def stats():
    """כתובת ישנה — מפנה לעמוד החודש."""
    return redirect(url_for("month_view"))


@app.route("/projects")
@login_required
def projects():
    """עמוד פרויקטים: תקציב לפרויקט — טיול, שיפוץ, אירוע ועוד."""
    user      = get_current_user()
    family_id = user["family_id"]
    project_list = db.get_projects(family_id, user["id"]) if family_id else []
    return render_template("projects.html", active_page="projects", user=user,
                           projects=project_list)


@app.route("/projects/<project_id>")
@login_required
def project_detail(project_id):
    user      = get_current_user()
    family_id = user["family_id"]
    project = db.get_project_detail(project_id, family_id, user["id"]) if family_id else None
    if not project:
        return redirect(url_for("projects"))
    return render_template("project_detail.html", active_page="projects", user=user,
                           project=project,
                           member_colors=_member_colors(family_id))


@app.route("/projects/<project_id>/edit")
@login_required
def project_edit(project_id):
    """מסך עריכת הגדרות הפרויקט (שם/תיאור/יעד/מעקב/שיתוף) + ניהול הקטגוריות —
    נפרד מעמוד התצוגה הנקי של הפרויקט."""
    user      = get_current_user()
    family_id = user["family_id"]
    project = db.get_project_detail(project_id, family_id, user["id"]) if family_id else None
    if not project:
        return redirect(url_for("projects"))
    return render_template("project_edit.html", active_page="projects", user=user,
                           project=project,
                           member_colors=_member_colors(family_id))


def _parse_project_body(body: dict):
    """מפענח ומאמת שדות משותפים ליצירה/עדכון של פרויקט (שם/יעד/סוגי מעקב
    בלבד — לא בעלות: זו נקבעת בנפרד ב-add_project_route, ומשתנה אחר כך רק
    דרך share_project_route/unshare_project_route).
    Returns (fields_dict, error) — fields_dict מוכן להעברה ל-db.add/update_project."""
    name = (body.get("name") or "").strip()
    if not name:
        return None, "נא להזין שם לפרויקט"

    budget_target, err = _parse_initial_balance({"initial_balance": body.get("budget_target")})
    if err:
        return None, "יעד תקציב חייב להיות מספר"

    description = (body.get("description") or "").strip()[:200] or None
    icon = (body.get("icon") or "").strip()[:16] or None

    track_expense = bool(body.get("track_expense", True))
    track_income  = bool(body.get("track_income", False))
    track_savings = bool(body.get("track_savings", False))
    if not (track_expense or track_income or track_savings):
        return None, "יש לבחור לפחות סוג עסקה אחד למעקב"

    return {
        "name": name, "budget_target": budget_target, "description": description,
        "icon": icon,
        "track_expense": track_expense, "track_income": track_income,
        "track_savings": track_savings,
    }, None


@app.route("/api/projects", methods=["POST"])
@login_required
def add_project_route():
    user = get_current_user()
    if not user["family_id"]:
        return jsonify({"error": "לא מצאנו את המשפחה שלך — רעננו את הדף, ואם זה חוזר התחברו מחדש"}), 400
    body = request.get_json(silent=True) or {}
    fields, err = _parse_project_body(body)
    if err:
        return jsonify({"error": err}), 422
    # אפשר ליצור פרויקט משותף או אישי עבור עצמו בלבד — אף פעם לא אישי
    # עבור בן משפחה אחר (owner_id נקבע כאן מהמשתמש המחובר, לא מהבקשה)
    is_personal = bool(body.get("is_personal"))
    owner_id = user["id"] if is_personal else None
    proj, err = db.add_project(user["family_id"], created_by=user["id"], owner_id=owner_id, **fields)
    if err:
        logger.error("add_project route: %s", err)
        return jsonify({"error": "יצירת הפרויקט נכשלה — נסה שוב"}), 500
    return jsonify(proj), 201


def project_access_required(f):
    """חוסם גישה לפרויקט אישי של בן משפחה אחר.

    הקריאה כבר הייתה מוגנת — ‎get_project_detail‎ ו-‎get_projects‎ מסננות
    פרויקט אישי שאינו של הצופה. הכתיבה לא: כל שמונת המסלולים סיננו לפי
    family_id בלבד. כלומר בן משפחה שניחש או ראה מזהה של פרויקט אישי יכול
    היה לערוך אותו, למחוק אותו על כל עסקאותיו, או לקרוא את הקטגוריות שלו
    — פרויקט שאסור לו אפילו לראות ברשימה.

    "לא נמצא" ולא "אין הרשאה" בכוונה: פרויקט אישי הוא פרטי, והתשובה
    אסור שתאשר שהוא קיים."""
    @wraps(f)
    def decorated(project_id, *args, **kwargs):
        user = get_current_user()
        project = db.get_project_for_transaction(project_id, user["family_id"])
        if not project:
            return jsonify({"error": "הפרויקט לא נמצא"}), 404
        if project.get("owner_id") and project["owner_id"] != user["id"]:
            return jsonify({"error": "הפרויקט לא נמצא"}), 404
        return f(project_id, *args, **kwargs)
    return decorated


@app.route("/api/projects/<project_id>", methods=["PUT"])
@login_required
@project_access_required
def update_project_route(project_id):
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    fields, err = _parse_project_body(body)
    if err:
        return jsonify({"error": err}), 422
    ok = db.update_project(project_id, user["family_id"], **fields)
    if not ok:
        return jsonify({"error": "עדכון נכשל"}), 500
    return jsonify({"status": "ok", **fields})


@app.route("/api/projects/<project_id>", methods=["DELETE"])
@login_required
@project_access_required
def delete_project_route(project_id):
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    delete_transactions = bool(body.get("delete_transactions"))
    ok = db.delete_project(project_id, user["family_id"], delete_transactions=delete_transactions)
    return jsonify({"status": "ok" if ok else "error"}), 200 if ok else 500


@app.route("/api/projects/<project_id>/share", methods=["PUT"])
@login_required
@project_access_required
def share_project_route(project_id):
    """הופך פרויקט אישי למשותף. רק הבעלים הנוכחי רשאי (נאכף ב-db.share_project)."""
    user = get_current_user()
    ok, err = db.share_project(project_id, user["family_id"], user["id"])
    if not ok:
        return jsonify({"error": _user_message(err)}), 422
    return jsonify({"status": "ok"})


@app.route("/api/projects/<project_id>/unshare", methods=["PUT"])
@login_required
@project_access_required
def unshare_project_route(project_id):
    """מחזיר פרויקט משותף להיות אישי. רק מי שיצר אותו במקור רשאי (נאכף ב-db.unshare_project)."""
    user = get_current_user()
    ok, err = db.unshare_project(project_id, user["family_id"], user["id"])
    if not ok:
        return jsonify({"error": _user_message(err)}), 422
    return jsonify({"status": "ok"})


@app.route("/api/projects", methods=["GET"])
@login_required
def list_projects_route():
    user = get_current_user()
    return jsonify(db.get_projects(user["family_id"], user["id"]) if user["family_id"] else [])


@app.route("/api/projects/<project_id>/categories", methods=["GET"])
@login_required
@project_access_required
def list_project_categories_route(project_id):
    user = get_current_user()
    type_ = request.args.get("type")
    return jsonify(db.get_project_categories(project_id, user["family_id"], type_))


@app.route("/api/projects/<project_id>/categories", methods=["POST"])
@login_required
@project_access_required
def add_project_category_route(project_id):
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "נא להזין שם קטגוריה"}), 422
    type_ = body.get("type")
    if type_ not in ("expense", "income", "savings"):
        return jsonify({"error": "סוג קטגוריה לא תקין"}), 422
    cat, err = db.add_project_category(project_id, user["family_id"], name,
                                       body.get("icon", "📦"), type_)
    if err:
        logger.error("add_project_category route: %s", err)
        return jsonify({"error": "הוספת הקטגוריה נכשלה — נסה שוב"}), 500
    return jsonify(cat), 201


@app.route("/api/projects/<project_id>/categories/<cat_id>", methods=["PUT"])
@login_required
@project_access_required
def update_project_category_route(project_id, cat_id):
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    icon = (body.get("icon") or "").strip() or "📦"
    if not name:
        return jsonify({"error": "נא להזין שם קטגוריה"}), 422
    ok = db.update_project_category(cat_id, project_id, user["family_id"], name, icon)
    if not ok:
        return jsonify({"error": "עדכון נכשל"}), 500
    return jsonify({"status": "ok", "name": name, "icon": icon})


@app.route("/api/projects/<project_id>/categories/<cat_id>", methods=["DELETE"])
@login_required
@project_access_required
def delete_project_category_route(project_id, cat_id):
    user = get_current_user()
    ok = db.delete_project_category(cat_id, project_id, user["family_id"])
    return jsonify({"status": "ok" if ok else "error"}), 200 if ok else 500


@app.route("/settings")
@login_required
def settings():
    user       = get_current_user()
    family_id  = user["family_id"]
    categories = db.get_categories(family_id)
    members    = db.get_family_members(family_id)       if family_id else []
    family     = db.get_family(family_id)               if family_id else {}
    recurring  = db.get_recurring_transactions(family_id, settings=family_settings()) if family_id else []
    projects   = db.get_projects(family_id, user["id"])  if family_id else []
    # הפרופיל שלי כבר נמצא ברשימת החברים שנשלפה למעלה — היא מחזירה שם
    # מלא, אימייל, טלפון ומקום עבודה לכל חבר. שליפה נוספת כאן הייתה
    # פנייה שלמה למסד בשביל נתון שכבר ביד.
    profile = next((m for m in members if m["id"] == user["id"]), None)
    if profile is None:
        # אין משפחה, או שהחבר לא חזר מהרשימה — נופלים לשליפה הישירה
        profile = db.get_profile(user["id"]) or {}
    # כמה עסקאות באמת עומדות להימחק. "פעולה סופית ולא ניתנת לביטול" הוא
    # משפט; מספר הוא עובדה, והוא מה שגורם לעצור.
    try:
        family_tx_count = db.family_transaction_count(family_id) if family_id else 0
    except db.DataUnavailable:
        family_tx_count = None

    full_name = profile.get("full_name") or profile.get("name") or user["name"]
    name_parts = full_name.split(" ", 1)
    account = {
        "full_name":  full_name,
        "first_name": name_parts[0] if name_parts else "",
        "last_name":  name_parts[1] if len(name_parts) > 1 else "",
        "email":      session.get("user_email", ""),
        "phone":      profile.get("phone") or "",
        "workplace":  profile.get("workplace") or "",
    }
    return render_template(
        "settings.html",
        family_tx_count=family_tx_count,
        active_page="settings",
        user=user,
        categories=categories,
        members=members,
        family=family,
        recurring=recurring,
        projects=projects,
        account=account,
    )


@app.route("/api/profile", methods=["PUT"])
@login_required
def update_profile():
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    first_name = (body.get("first_name") or "").strip()
    last_name  = (body.get("last_name") or "").strip()
    phone      = _normalize_phone(body.get("phone") or "")
    workplace  = (body.get("workplace") or "").strip()
    workplace_scope = body.get("workplace_scope")  # 'all' | 'future' | None

    if not first_name or not last_name:
        return jsonify({"error": "נא למלא שם פרטי ושם משפחה"}), 422
    # ריק מותר כאן (השדה אינו חובה בעריכה), אבל מה שהוקלד חייב להיות מספר
    if phone and not _looks_like_phone(phone):
        return jsonify({"error": "מספר הטלפון אינו תקין — למשל 050-1234567"}), 422

    old_profile = db.get_profile(user["id"]) or {}
    old_workplace = old_profile.get("workplace") or ""

    full_name = f"{first_name} {last_name}"
    ok, err = db.update_profile(user["id"], full_name, phone or None, workplace or None)
    if not ok:
        return jsonify({"error": _user_message(err, "עדכון הפרטים נכשל")}), 500

    # מקום עבודה השתנה בפועל וסופק סקופ — מיישמים על היסטוריית עסקאות המשכורת
    if workplace_scope and workplace != old_workplace and user["family_id"]:
        db.update_workplace_history(
            user["id"], user["family_id"], workplace or None, old_workplace or None,
            apply_to_all=(workplace_scope == "all"),
        )

    # השם הפרטי מוצג בכל האתר (ברכות, עסקאות וכו') — לעדכן גם בסשן
    session["user_name"] = db.first_name(full_name)
    return jsonify({"status": "ok", "full_name": full_name, "first_name": first_name,
                    "last_name": last_name, "phone": phone, "workplace": workplace})


@app.route("/api/profile/password", methods=["PUT"])
@login_required
# מאמת את הסיסמה הנוכחית מול Supabase, כלומר אורקל לניחוש סיסמאות למי
# שהשיג סשן. ההגבלה על /login לא עוזרת כאן — זה מסלול אחר.
@limiter.limit("5 per minute")
def update_password():
    body             = request.get_json(silent=True) or {}
    current_password = body.get("current_password", "")
    password         = body.get("password", "")
    password_confirm = body.get("password_confirm", "")

    if not current_password:
        return jsonify({"error": "נא להזין את הסיסמה הנוכחית"}), 422
    if len(password) < 6:
        return jsonify({"error": "הסיסמה החדשה חייבת להכיל לפחות 6 תווים"}), 422
    if password != password_confirm:
        return jsonify({"error": "הסיסמאות החדשות אינן תואמות"}), 422

    # מוודאים שהסיסמה הנוכחית נכונה לפני שמאפשרים להחליף אותה
    _, err = db.sign_in(session.get("user_email", ""), current_password)
    if err:
        return jsonify({"error": "הסיסמה הנוכחית שגויה"}), 403

    ok, err = db.update_password(session.get("access_token"), password)
    if not ok:
        return jsonify({"error": _user_message(err, "עדכון הסיסמה נכשל")}), 500
    return jsonify({"status": "ok"})


@app.route("/api/account/reset", methods=["POST"])
@login_required
# אורקל סיסמה, ובנוסף פעולה הרסנית: מוחקת את כל עסקאות המשפחה.
# מחמיר יותר — אין תרחיש לגיטימי של איפוס חוזר.
@limiter.limit("3 per hour")
def reset_account_route():
    """איפוס עסקאות: מוחק את כל העסקאות (הכנסות/הוצאות/חיסכון, כולל קבועות)
    לפי הבחירה — של כל המשפחה או רק של המשתמש. החשבון, הקטגוריות, הפרויקטים
    וההגדרות נשמרים. דורש אימות סיסמה. הנמחק מארוכב בארכיון הפנימי."""
    user     = get_current_user()
    body     = request.get_json(silent=True) or {}
    password = body.get("password", "")
    scope    = body.get("scope", "family")  # 'family' | 'mine'

    if not password:
        return jsonify({"error": "נא להזין את הסיסמה הנוכחית"}), 422
    if scope not in ("family", "mine"):
        return jsonify({"error": "קלט לא תקין"}), 422

    response, err = db.sign_in(session.get("user_email", ""), password)
    if err:
        return jsonify({"error": "הסיסמה שגויה"}), 403

    db.set_auth_token(response.session.access_token)

    # איפוס כל המשפחה הוא הפעולה ההרסנית ביותר באפליקציה, והוא היה
    # פתוח לכל חבר עם הסיסמה של עצמו בלבד. "רק שלי" נשאר פתוח — זה
    # הכסף של מי שמבקש.
    if scope == "family":
        denied = _require_manager()
        if denied:
            return denied

    # ‎deleted‎ ולא ‎ok‎: אפס שורות הוא תוצאה תקינה (משפחה בלי עסקאות),
    # אז הכישלון נמדד לפי ‎err‎ בלבד. המספר מוחזר כדי שהמשתמש יראה מה
    # באמת קרה — זו הפעולה ההרסנית ביותר באפליקציה.
    deleted, err = db.reset_transactions(
        user["family_id"],
        only_user_id=user["id"] if scope == "mine" else None,
    )
    if err:
        logger.error("reset_transactions route: %s", err)
        return jsonify({"error": "האיפוס נכשל"}), 500
    return jsonify({"status": "ok", "deleted": deleted})


@app.route("/api/account", methods=["DELETE"])
@login_required
# אורקל סיסמה, והפעולה הכי הרסנית באפליקציה — מחיקת חשבון לצמיתות.
@limiter.limit("3 per hour")
def delete_account_route():
    """מחיקת חשבון לצמיתות. מבחינת המשתמש הכל נמחק והמייל/טלפון משתחררים;
    בפועל הנתונים מארוכבים לארכיון הפנימי של בעל האתר (ראה מיגרציית
    20260711100000). דורש אימות סיסמה נוכחית."""
    body     = request.get_json(silent=True) or {}
    password = body.get("password", "")

    if not password:
        return jsonify({"error": "נא להזין את הסיסמה הנוכחית"}), 422

    # אימות סיסמה — גם מגן ממחיקה בטעות וגם מרענן את הטוקן שאיתו נמחק
    response, err = db.sign_in(session.get("user_email", ""), password)
    if err:
        return jsonify({"error": "הסיסמה שגויה"}), 403

    db.set_auth_token(response.session.access_token)
    ok, err = db.delete_my_account()
    if not ok:
        return jsonify({"error": "מחיקת החשבון נכשלה"}), 500

    session.clear()
    # מחיקת חשבון היא מחיקה — לא משאירים אחריה את המזהה ולא את סימון
    # המכשיר. מי שיפתח את הכתובת אחר כך הוא שוב אורח שרואה את דף הנחיתה.
    response = jsonify({"status": "ok"})
    response.delete_cookie(_LAST_ID_COOKIE, samesite="Lax", secure=not _IS_DEV)
    response.delete_cookie(_DEVICE_COOKIE,  samesite="Lax", secure=not _IS_DEV)
    return response


def _parse_amount(raw):
    """פרסינג בטוח של סכום עסקה: מספר סופי וחיובי בלבד.
    מחזיר (value, error) — error בעברית מוצג למשתמש כ-422."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, "הסכום חייב להיות מספר"
    if not math.isfinite(value) or value <= 0:
        return None, "הסכום חייב להיות מספר חיובי"
    # העמודה היא NUMERIC(10,2) ומתפוצצת מעל 99,999,999.99. בלי הבדיקה
    # הזאת הקלדה שגויה של תשע ספרות מגיעה ל-Postgres, נכשלת שם, וחוזרת
    # כ"הוספת העסקה נכשלה — נסה שוב" — כך שהמשתמש מנסה שוב את אותו קלט
    # ונכשל שוב, בלי שום רמז למה.
    if value > 99_999_999:
        return None, "הסכום גדול מדי"
    # מתחת לאגורה מתעגל ל-0.00 ואז נופל על ה-CHECK של העמודה, עם אותה
    # הודעה גנרית ואותו מבוי סתום
    if round(value, 2) <= 0:
        return None, "הסכום קטן מדי"
    return value, None


# כמה שנים אחורה וקדימה עסקה עדיין הגיונית. רחב בכוונה — אנשים מזינים
# היסטוריה מהעבר ומקדימים תשלומים לעתיד — וצר מספיק כדי לתפוס אסון.
_DATE_PAST_YEARS   = 10
_DATE_FUTURE_YEARS = 5


def _parse_date(raw):
    """פרסינג בטוח של תאריך עסקה. מחזיר (iso_string, error).

    ‎date‎ עבר עד היום מגוף הבקשה אל המסד בלי שום בדיקה, ולעמודה לא היה
    אילוץ. זה לא נשאר תיאורטי בגלל מנוע העסקאות הקבועות: תבנית עם
    תאריך התחלה בשנת 1000 גורמת לו לייצר מופע לכל חודש מאז, עד תקרת
    500 השורות — 500 עסקאות אמיתיות בקריאה אחת, שנכנסות לסיכומים
    ולהשוואת החודשים לתמיד.

    האילוץ במסד (‎transactions_date_sane‎) הוא הרשת האחרונה והוא רחב,
    כי CHECK חייב להיות immutable ולא יכול לדעת מה היום. כאן אפשר."""
    if not isinstance(raw, str):
        return None, "התאריך חסר או אינו תקין"
    try:
        value = date.fromisoformat(raw.strip())
    except ValueError:
        return None, "התאריך אינו תקין"
    today = clock.today()
    if value.year < today.year - _DATE_PAST_YEARS:
        return None, "התאריך רחוק מדי בעבר"
    if value.year > today.year + _DATE_FUTURE_YEARS:
        return None, "התאריך רחוק מדי בעתיד"
    return value.isoformat(), None


def _require_manager():
    """שער לפעולות הרסניות. מחזיר ‎None‎ אם מותר, או תשובת שגיאה מוכנה.

    התפקיד נוסף כדי שמישהו יהיה אחראי, אבל נאכף רק על הסרת חבר — כך
    שכל מי שהצטרף עם קוד בן שישה תווים יכול היה למחוק את היסטוריית
    כל המשפחה, למחוק קטגוריות ולהחליף את קוד ההזמנה.

    הבדיקה נגזרת מ-‎auth.uid()‎ במסד ולא מהסשן, ולכן אי אפשר לזייף
    אותה מהלקוח. בכישלון שליפה מסרבים — "לא ידוע אם הוא מנהל" הוא
    לא "כן"."""
    try:
        if db.is_family_manager():
            return None
    except db.DataUnavailable:
        return jsonify({"error": "לא הצלחנו לאמת הרשאות — נסו שוב"}), 503
    return jsonify({
        "error": "רק מנהל המשפחה יכול לבצע את הפעולה הזאת.",
    }), 403


def _resolve_owner(body: dict, user: dict, tx_type: str):
    """מי הבעלים של העסקה — לפי העדפות המשפחה: סוג שהשיוך כבוי בו נשמר
    תמיד כמשפחתי (NULL), גם אם הבקשה ניסתה לשלוח בעלים.
    ערכים: uuid של בן משפחה, "shared" = משותפת (NULL), ובלי owner — המחובר.
    מחזירה (user_id, error)."""
    if not family_settings().get("owner_attribution", {}).get(tx_type, False):
        return None, None
    owner = body.get("owner")
    if owner == "shared":
        return None, None
    if owner:
        # ה-uuid הגיע מהלקוח והתקבל עד היום כמו שהוא. RLS בודקת רק את
        # family_id בשורה שנכתבת, לא את user_id, אז אפשר היה לרשום עסקה
        # על שם מי שלא במשפחה — או לתלות הוצאה על בן הזוג. זו לא דליפת
        # מידע אלא זיוף שיוך, וזה מספיק: הפילוח "לפי בן משפחה" מתבסס עליו.
        if owner not in {m["id"] for m in db.get_family_members(user["family_id"])}:
            return None, "בן המשפחה שנבחר אינו במשפחה שלך"
        return owner, None
    return user["id"], None


def _apply_project_assignment(body: dict, user: dict, tx_type: str):
    """מיישם שיוך לפרויקט (אם body['project_id'] נשלח): מוודא שהפרויקט
    עוקב אחרי סוג העסקה הזה, אוכף בשרת שיוך אוטומטי לבעלים בפרויקט אישי
    (מתעלם מ-body['owner'] במקרה הזה), ומחליף את הקטגוריה הרגילה בקטגוריית
    הפרויקט הייעודית. Returns (project_id, project_category_id, category_id, user_id, error)."""
    project_id = body.get("project_id")
    if not project_id:
        owner_id, owner_err = _resolve_owner(body, user, tx_type)
        if owner_err:
            return None, None, None, None, owner_err
        category_id, cat_err = _validated_category(body.get("category_id"), user, tx_type)
        if cat_err:
            return None, None, None, None, cat_err
        return None, None, category_id, owner_id, None

    project = db.get_project_for_transaction(project_id, user["family_id"])
    if not project:
        return None, None, None, None, "הפרויקט לא נמצא"

    # פרויקט אישי: רק הבעלים רשאי לכתוב אליו. הקריאה כבר מוסתרת מאחרים
    # (‎_filter_hidden_personal_projects‎), אבל הכתיבה לא נבדקה — כך שבן
    # משפחה יכול היה לרשום עסקאות לתוך פרויקט שאסור לו אפילו לראות.
    if project.get("owner_id") and project["owner_id"] != user["id"]:
        return None, None, None, None, "הפרויקט לא נמצא"

    track_key = {"expense": "track_expense", "income": "track_income", "savings": "track_savings"}[tx_type]
    if not project.get(track_key):
        return None, None, None, None, "הפרויקט הזה לא עוקב אחרי סוג העסקה הזה"

    owner_id = project.get("owner_id")
    if owner_id:
        user_id, owner_err = owner_id, None
    else:
        user_id, owner_err = _resolve_owner(body, user, tx_type)
    if owner_err:
        return None, None, None, None, owner_err

    # קטגוריית הפרויקט חייבת להיות של הפרויקט הזה, לא של אחר
    project_category_id = body.get("project_category_id")
    if project_category_id:
        valid = {c["id"] for c in db.get_project_categories(project_id, user["family_id"])}
        if project_category_id not in valid:
            return None, None, None, None, "הקטגוריה אינה שייכת לפרויקט הזה"

    return project_id, project_category_id, None, user_id, None


def _validated_category(category_id, user: dict, tx_type: str):
    """מוודא שהקטגוריה קיימת במשפחה ומתאימה לסוג העסקה.
    מחזירה (category_id, error). ריק הוא ערך תקין — עסקה ללא קטגוריה."""
    if not category_id:
        return None, None
    for cat in db.get_categories(user["family_id"]):
        if cat["id"] == category_id:
            if cat.get("type") != tx_type:
                return None, "הקטגוריה אינה מתאימה לסוג העסקה"
            return category_id, None
    return None, "הקטגוריה לא נמצאה"


# ─── API: Transactions ────────────────────────────────────────────────────────

@app.route("/api/family/members", methods=["GET"])
@login_required
def family_members():
    user = get_current_user()
    members = db.get_family_members(user["family_id"]) if user["family_id"] else []
    return jsonify([{"id": m["id"], "name": m["name"]} for m in members])

@app.route("/api/transactions", methods=["POST"])
@login_required
def add_transaction():
    user = get_current_user()
    if not user["family_id"]:
        return jsonify({"error": "לא מצאנו את המשפחה שלך — רעננו את הדף, ואם זה חוזר התחברו מחדש"}), 400

    body = request.get_json(silent=True) or {}

    required = ("amount", "type", "date")
    if not all(body.get(k) for k in required):
        return jsonify({"error": "חסרים פרטים: סכום, סוג ותאריך הם שדות חובה"}), 422

    tx_type = body["type"]
    if tx_type not in ("expense", "income", "savings"):
        return jsonify({"error": "סוג העסקה חייב להיות הוצאה, הכנסה או חיסכון"}), 422

    amount, amount_err = _parse_amount(body["amount"])
    if amount_err:
        return jsonify({"error": amount_err}), 422

    tx_date, date_err = _parse_date(body["date"])
    if date_err:
        return jsonify({"error": date_err}), 422

    recurring_end = body.get("recurring_end_date") or None
    if recurring_end:
        recurring_end, end_err = _parse_date(recurring_end)
        if end_err:
            return jsonify({"error": f"תאריך הסיום: {end_err}"}), 422
        if recurring_end < tx_date:
            return jsonify({"error": "תאריך סיום הסדרה מוקדם מתאריך ההתחלה"}), 422

    project_id, project_category_id, category_id, owner_user_id, proj_err = \
        _apply_project_assignment(body, user, tx_type)
    if proj_err:
        return jsonify({"error": proj_err}), 422

    # הכנסת משכורת חדשה: מתעדים ("מקפיאים") את מקום העבודה הנוכחי של הבעלים
    # על העסקה עצמה, כדי ששינוי מקום עבודה עתידי לא ישנה בשקט את מה שכבר
    # נוצר — ראה update_workplace_history לזרימה של שינוי מקום עבודה בפועל.
    workplace_snapshot = None
    if tx_type == "income" and owner_user_id and category_id:
        cat = next((c for c in db.get_categories(user["family_id"]) if c["id"] == category_id), None)
        if cat and "משכורת" in cat.get("name", ""):
            owner_profile = db.get_profile(owner_user_id)
            workplace_snapshot = (owner_profile or {}).get("workplace")

    payload = {
        "amount":      amount,
        "type":        tx_type,
        "date":        tx_date,
        "description": body.get("description", ""),
        "category_id": category_id,
        "user_id":     owner_user_id,
        "family_id":   user["family_id"],
        "is_recurring":         bool(body.get("is_recurring", False)),
        "recurring_frequency":  body.get("recurring_frequency"),
        "recurring_end_date":   recurring_end,
        "project_id":           project_id,
        "project_category_id":  project_category_id,
        "workplace":            workplace_snapshot,
    }
    # קבלה מצורפת אפשרית רק בהוצאות; ריק = לא נוגעים בעמודה (לא מוחקים קבלה קיימת בעריכה)
    if tx_type == "expense" and body.get("receipt_path"):
        payload["receipt_path"] = body["receipt_path"]

    result, err = db.add_transaction(payload)
    if err:
        logger.error("add_transaction route: %s", err)
        return jsonify({"error": "הוספת העסקה נכשלה — נסה שוב"}), 500

    # עסקה קבועה חדשה (גם רטרואקטיבית) — משלימים מיד את כל המופעים עד היום
    if payload["is_recurring"]:
        db.materialize_recurring(user["family_id"])   # (created, ok) — כאן לא נדרש

    return jsonify({"status": "ok", "transaction": result}), 201


@app.route("/api/transactions/<tx_id>", methods=["PUT"])
@login_required
def update_transaction(tx_id):
    user = get_current_user()
    if not user["family_id"]:
        return jsonify({"error": "לא מצאנו את המשפחה שלך — רעננו את הדף, ואם זה חוזר התחברו מחדש"}), 400

    body = request.get_json(silent=True) or {}

    required = ("amount", "type", "date")
    if not all(body.get(k) for k in required):
        return jsonify({"error": "חסרים פרטים: סכום, סוג ותאריך הם שדות חובה"}), 422

    tx_type = body["type"]
    if tx_type not in ("expense", "income", "savings"):
        return jsonify({"error": "סוג העסקה חייב להיות הוצאה, הכנסה או חיסכון"}), 422

    amount, amount_err = _parse_amount(body["amount"])
    if amount_err:
        return jsonify({"error": amount_err}), 422

    tx_date, date_err = _parse_date(body["date"])
    if date_err:
        return jsonify({"error": date_err}), 422

    recurring_end = body.get("recurring_end_date") or None
    if recurring_end:
        recurring_end, end_err = _parse_date(recurring_end)
        if end_err:
            return jsonify({"error": f"תאריך הסיום: {end_err}"}), 422
        if recurring_end < tx_date:
            return jsonify({"error": "תאריך סיום הסדרה מוקדם מתאריך ההתחלה"}), 422

    project_id, project_category_id, category_id, owner_user_id, proj_err = \
        _apply_project_assignment(body, user, tx_type)
    if proj_err:
        return jsonify({"error": proj_err}), 422

    # מופע של סדרה לא יכול להפוך לתבנית בפני עצמה. אין אילוץ במסד שמונע
    # את זה, והתוצאה היא שתי סדרות מקבילות שמייצרות את אותו כסף פעמיים
    # בכל חודש, לתמיד. מי שרוצה לשנות את הסדרה עושה זאת מהתבנית עצמה.
    if bool(body.get("is_recurring", False)):
        try:
            if db.is_recurring_instance(tx_id, user["family_id"]):
                return jsonify({
                    "error": "העסקה הזאת כבר חלק מסדרה קבועה. כדי לשנות את "
                             "הסדרה, ערכו אותה דרך ההגדרות ← עסקאות קבועות.",
                }), 422
        except db.DataUnavailable:
            # לא ידוע. סדרה כפולה היא נזק שאי אפשר לבטל; ניסיון חוזר לא.
            return jsonify({"error": "לא הצלחנו לבדוק את הסדרה הקבועה — נסו שוב"}), 503

    payload = {
        "amount":      amount,
        "type":        tx_type,
        "date":        tx_date,
        "description": body.get("description", ""),
        "category_id": category_id,
        "user_id":     owner_user_id,
        "is_recurring":         bool(body.get("is_recurring", False)),
        "recurring_frequency":  body.get("recurring_frequency"),
        "recurring_end_date":   recurring_end,
        "project_id":           project_id,
        "project_category_id":  project_category_id,
    }
    # קבלה מצורפת אפשרית רק בהוצאות; ריק = לא נוגעים בעמודה (לא מוחקים קבלה קיימת בעריכה)
    if tx_type == "expense" and body.get("receipt_path"):
        payload["receipt_path"] = body["receipt_path"]

    result, err = db.update_transaction(tx_id, user["family_id"], payload)
    if err:
        logger.error("update_transaction route: %s", err)
        return jsonify({"error": "עדכון העסקה נכשל — נסה שוב"}), 500
    # אף שורה לא נגעה: העסקה נמחקה בינתיים על ידי בן משפחה אחר, או
    # שהמזהה שייך למשפחה אחרת. עד היום זה חזר כ-200 "נשמר", והמשתמש
    # האמין שהעריכה שלו נקלטה.
    if not result:
        return jsonify({"error": "העסקה לא נמצאה — ייתכן שנמחקה בינתיים"}), 404

    if payload["is_recurring"]:
        db.materialize_recurring(user["family_id"])   # (created, ok) — כאן לא נדרש

    return jsonify({"status": "ok", "transaction": result})


@app.route("/api/transactions/<tx_id>", methods=["DELETE"])
@login_required
def delete_transaction(tx_id):
    """מחיקת עסקה — ועסקה קבועה היא לא עסקה אחת.

    השאלה היא בדיוק זו של יומן: "רק את זו" או "את זו וכל הבאות". אין
    כאן הבחנה בין "תבנית" למופע — היא פנימית לגמרי, ולמי שמוחק את שכר
    הדירה של מרץ לא אמור להיות אכפת אם מרץ הוא במקרה החודש שבו הסדרה
    נפתחה.

    בלי ‎mode‎ מוחזר 409 עם מספר המופעים שיימחקו ב"כל הבאות", כדי
    שהשאלה תוצג עם המספר האמיתי — אותו דפוס של ‎/api/family/join‎."""
    user = get_current_user()
    mode = request.args.get("mode")

    try:
        occurrence, _ = db.recurring_occurrence(tx_id, user["family_id"])
    except db.DataUnavailable:
        # לא ידוע אם יש סדרה מאחורי השורה. מחיקה עיוורת כאן היא בדיוק
        # הנזק שאי אפשר לבטל, אז מסרבים.
        return jsonify({"error": "לא הצלחנו לבדוק אם זו עסקה קבועה — נסו שוב"}), 503

    if occurrence and mode not in ("one", "later"):
        return jsonify({"needs_choice": True, "later": occurrence["later"]}), 409

    if occurrence and mode == "one":
        ok, err = db.delete_one_occurrence(
            tx_id, occurrence["template_id"], occurrence["date"], user["family_id"])
        if not ok:
            if err == "not found":
                return jsonify({"error": "העסקה לא נמצאה"}), 404
            logger.error("delete_one_occurrence route: %s", err)
            return jsonify({"error": "המחיקה נכשלה — נסו שוב"}), 500
        return jsonify({"status": "ok", "deleted": 1})

    if occurrence and mode == "later":
        deleted, err = db.delete_occurrences_from(
            occurrence["template_id"], occurrence["date"], user["family_id"])
        if err:
            logger.error("delete_occurrences_from route: %s", err)
            return jsonify({"error": "המחיקה נכשלה — נסו שוב"}), 500
        return jsonify({"status": "ok", "deleted": deleted})

    receipt_path = db.get_transaction_receipt_path(tx_id, user["family_id"])
    ok = db.delete_transaction(tx_id, user["family_id"])
    if ok and receipt_path:
        db.delete_receipt(session.get("access_token"), receipt_path)
    return jsonify({"status": "ok" if ok else "error"}), 200 if ok else 500


@app.route("/api/recurring/<template_id>", methods=["DELETE"])
@login_required
def stop_recurring_route(template_id):
    """עוצר סדרה קבועה. במכוון לא מוחק את השורה: היא המופע הראשון בסדרה,
    כלומר כסף שבאמת זז, והדיאלוג בהגדרות מבטיח שמה שכבר נוצר יישאר.
    מי שרוצה למחוק את העסקה עצמה עושה זאת מרשימת העסקאות כמו בכל עסקה."""
    user = get_current_user()
    if not user["family_id"]:
        return jsonify({"error": "לא משויכת משפחה לחשבון"}), 400

    ok, err = db.stop_recurring(template_id, user["family_id"])
    if not ok:
        if err == "not found":
            return jsonify({"error": "העסקה הקבועה לא נמצאה"}), 404
        logger.error("stop_recurring route: %s", err)
        return jsonify({"error": "ההסרה נכשלה — נסה שוב"}), 500
    return jsonify({"status": "ok"})


@app.route("/api/recurring/<template_id>/sync", methods=["PUT"])
@login_required
def sync_recurring_template(template_id):
    """סנכרון חכם: מעדכן את התבנית הקבועה עצמה (לא מופע בודד), כך שרק
    מופעים עתידיים שעוד לא נוצרו ישתמשו בערך החדש."""
    user = get_current_user()
    if not user["family_id"]:
        return jsonify({"error": "לא מצאנו את המשפחה שלך — רעננו את הדף, ואם זה חוזר התחברו מחדש"}), 400

    body = request.get_json(silent=True) or {}

    # זה היה המסלול הכותב היחיד שלא עבר ב-_parse_amount ולא אימת קטגוריה:
    # ‎float()‎ חשוף קיבל ‎-5000‎ ו-‎inf‎, שנעצרו רק ב-CHECK של המסד וחזרו
    # למשתמש כ-500 סתום; ו-‎category_id‎ נכתב בלי שום בדיקת שייכות, כך
    # שתבנית יכלה להצביע על קטגוריה של משפחה אחרת.
    amount = body.get("amount")
    if amount is not None:
        amount, amount_err = _parse_amount(amount)
        if amount_err:
            return jsonify({"error": amount_err}), 422

    category_id = body.get("category_id")
    if category_id is not None:
        try:
            tx_type = db.transaction_type(template_id, user["family_id"])
        except db.DataUnavailable:
            return jsonify({"error": "לא הצלחנו לאמת את הקטגוריה — נסו שוב"}), 503
        if tx_type is None:
            return jsonify({"error": "התבנית הקבועה לא נמצאה"}), 404
        category_id, cat_err = _validated_category(category_id, user, tx_type)
        if cat_err:
            return jsonify({"error": cat_err}), 422

    result, err = db.update_recurring_template(
        template_id, user["family_id"],
        amount=amount,
        category_id=category_id,
        description=body.get("description"),
    )
    if err:
        logger.error("update_recurring_template route: %s", err)
        return jsonify({"error": "עדכון העסקה הקבועה נכשל — נסה שוב"}), 500
    if not result:
        return jsonify({"error": "התבנית הקבועה לא נמצאה"}), 404
    return jsonify({"status": "ok", "transaction": result})


# ─── API: Receipt scanning (צילום קבלה) ───────────────────────────────────────

@app.route("/api/receipts/scan", methods=["POST"])
# המסלול היחיד כאן שעולה כסף אמיתי, והיחיד מבין 23 המסלולים הכותבים
# שלא הייתה עליו שום הגבלה. סריקה אחת לוקחת 2-6 שניות, אז עשר לדקה
# לא נוגעות באף אדם — הן נוגעות בסקריפט.
@limiter.limit("10 per minute")
@login_required
def scan_receipt_route():
    user = get_current_user()
    if not user["family_id"]:
        return jsonify({"error": "לא מצאנו את המשפחה שלך — רעננו את הדף, ואם זה חוזר התחברו מחדש"}), 400

    try:
        used = db.receipt_scans_this_month(user["family_id"])
        used_globally = db.receipt_scans_globally_this_month()
    except db.DataUnavailable:
        # לא ידוע כמה נוצל. הכיוון הבטוח הוא לסרב: אישור כשהבדיקה נכשלה
        # מבטל בפועל את ההגבלה על חשבון ה-OpenAI, וזו הוצאה אמיתית.
        return jsonify({
            "error": "לא הצלחנו לבדוק את מכסת הסריקות — נסו שוב, או הזינו ידנית.",
        }), 503

    # התקרה הגלובלית נבדקת לפני זו של המשפחה: כשהיא נחצית זו לא אשמתו
    # של מי שעומד כאן, וההודעה צריכה לומר את זה ולא להאשים אותו במכסה
    # שהוא לא ניצל.
    if used_globally >= db.RECEIPT_GLOBAL_MONTHLY_LIMIT:
        logger.error("סריקות קבלות: נחצתה התקרה הגלובלית (%s)", used_globally)
        return jsonify({
            "error": "סריקת הקבלות אינה זמינה כרגע. ניתן להזין את הפרטים ידנית.",
        }), 503

    if used >= db.RECEIPT_MONTHLY_LIMIT:
        return jsonify({
            "error": f"הגעתם למכסת הסריקות החודשית ({db.RECEIPT_MONTHLY_LIMIT}). ניתן להמשיך ולהזין ידנית.",
        }), 429

    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"error": "לא התקבלה תמונה"}), 422

    # ולידציית סוג הקובץ לפני קריאה/אחסון — אותו whitelist של הסריקה עצמה
    if (file.mimetype or "") not in db._RECEIPT_MEDIA_TYPES:
        return jsonify({"error": "סוג הקובץ לא נתמך — נא לצלם או לבחור תמונה (JPG/PNG/WebP)"}), 422

    image_bytes = file.read()
    if not image_bytes:
        return jsonify({"error": "לא התקבלה תמונה"}), 422
    if len(image_bytes) > 6 * 1024 * 1024:
        return jsonify({"error": "התמונה גדולה מדי — נסה שוב עם תמונה קטנה יותר"}), 413

    all_categories = db.get_categories(user["family_id"])
    expense_category_names = [c["name"] for c in all_categories if c.get("type") == "expense"]

    data, err = db.scan_receipt(image_bytes, file.mimetype or "image/jpeg", expense_category_names)
    if err:
        return jsonify({"error": err}), 422

    # סריקה מוצלחת: נספרת במכסה גם אם העלאת התמונה לאחסון נכשלה
    db.record_receipt_scan(user["family_id"], user["id"])

    receipt_path, upload_err = db.upload_receipt(
        session.get("access_token"), user["family_id"], image_bytes, file.mimetype or "image/jpeg"
    )
    if upload_err:
        receipt_path = None

    category_id = None
    if data.get("category_name"):
        for c in all_categories:
            if c.get("type") == "expense" and c.get("name") == data["category_name"]:
                category_id = c["id"]
                break

    return jsonify({
        "status":       "ok",
        "amount":       data["amount"],
        "merchant":     data["merchant"],
        "date":         data["date"],
        "category_id":  category_id,
        "receipt_path": receipt_path,
    })


@app.route("/receipts/<tx_id>", methods=["GET"])
@login_required
def view_receipt(tx_id):
    """מפנה לקבלה המצורפת לעסקה.

    הפניה ולא JSON, וזו הנקודה כולה: קודם הסמל שלף את הכתובת ב-fetch ואז
    קרא ל-window.open. ב-iOS זה נחסם תמיד — הדפדפן מתיר פתיחת חלון רק
    כתוצאה ישירה מלחיצה, וההמתנה לשרת מבטלת את הקשר. אין חלון, אין שגיאה,
    לא קורה כלום. בפועל הקבלות שנסרקו לא היו נגישות מהטלפון בכלל.

    עכשיו הסמל הוא קישור רגיל, והדפדפן מנווט בעצמו — ניווט שנובע מלחיצה
    לא נחסם. הכתובת החתומה נוצרת כאן ולא נשלחת ללקוח מראש, כך שהיא גם לא
    יושבת ב-HTML של כל שורה עם קבלה.

    ‎/receipts/‎ ולא ‎/api/receipts/‎ כי זה ניווט של הדפדפן: תחת ‎/api/‎ סשן
    שפג היה מחזיר 401 JSON ללשונית חדשה, במקום להעביר להתחברות."""
    user = get_current_user()
    path = db.get_transaction_receipt_path(tx_id, user["family_id"])
    if not path:
        return render_template("error.html", code=404,
                               message="לא נמצאה קבלה מצורפת לעסקה הזו"), 404

    url, err = db.get_receipt_signed_url(session.get("access_token"), path)
    if err or not url:
        logger.error("receipt signed url: %s", err)
        return render_template("error.html", code=500,
                               message="טעינת הקבלה נכשלה — נסו שוב בעוד רגע"), 500

    response = redirect(url)
    # הכתובת החתומה קצרת-מועד ואישית; אסור שתישמר במטמון של proxy
    response.headers["Cache-Control"] = "no-store"
    return response


# ─── API: Categories ──────────────────────────────────────────────────────────

@app.route("/api/categories", methods=["GET"])
@login_required
def get_categories():
    user = get_current_user()
    cats = db.get_categories(user["family_id"])
    return jsonify(cats)


def _parse_initial_balance(body: dict):
    """יתרה התחלתית רלוונטית רק לקטגוריות חיסכון. ריק/חסר = None (ללא יתרה)."""
    raw = body.get("initial_balance")
    if raw in (None, ""):
        return None, None
    try:
        return float(raw), None
    except (TypeError, ValueError):
        return None, "יתרה התחלתית חייבת להיות מספר"


@app.route("/api/categories", methods=["POST"])
@login_required
def add_category():
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    cat, err = db.add_custom_category(
        family_id=user["family_id"],
        name=body.get("name", ""),
        icon=body.get("icon", "📦"),
        type_=body.get("type", "expense"),
    )
    if err:
        logger.error("add_category route: %s", err)
        return jsonify({"error": "הוספת הקטגוריה נכשלה — נסה שוב"}), 500
    return jsonify(cat), 201


@app.route("/api/categories/<cat_id>", methods=["PUT"])
@login_required
def update_category(cat_id):
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    icon = (body.get("icon") or "").strip() or "📦"
    if not name:
        return jsonify({"error": "נא להזין שם קטגוריה"}), 422
    ok = db.update_category(cat_id, user["family_id"], name, icon)
    if not ok:
        return jsonify({"error": "עדכון נכשל"}), 500
    return jsonify({"status": "ok", "name": name, "icon": icon})


# ─── API: Categories delete ───────────────────────────────────────────────────

@app.route("/api/categories/<cat_id>", methods=["DELETE"])
@login_required
def delete_category(cat_id):
    user = get_current_user()

    denied = _require_manager()
    if denied:
        return denied

    client = db.get_client()
    if not client:
        return jsonify({"error": "השירות אינו זמין כרגע — נסו שוב בעוד רגע"}), 500
    try:
        # ‎.data‎ מחזיר את מה שנמחק בפועל. בלי הבדיקה הזאת המסלול ענה
        # "נמחק" גם כשלא נגע בכלום — קטגוריה שאינה מותאמת אישית, או
        # מזהה של משפחה אחרת.
        result = client.table("categories") \
            .delete() \
            .eq("id", cat_id) \
            .eq("family_id", user["family_id"]) \
            .eq("is_custom", True) \
            .execute()
        if not result.data:
            return jsonify({"error": "הקטגוריה לא נמצאה"}), 404
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.exception("delete_category route")
        return jsonify({"error": "מחיקת הקטגוריה נכשלה — נסה שוב"}), 500


@app.route("/api/categories/reorder", methods=["PUT"])
@login_required
def reorder_categories_route():
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    type_ = body.get("type")
    order = body.get("order") or []
    if type_ not in ("income", "expense", "savings") or not isinstance(order, list) or not order:
        return jsonify({"error": "קלט לא תקין"}), 422
    ok = db.reorder_categories(user["family_id"], type_, order)
    if not ok:
        return jsonify({"error": "עדכון הסדר נכשל"}), 500
    return jsonify({"status": "ok"})


# ─── API: Family ──────────────────────────────────────────────────────────────

@app.route("/api/family/settings", methods=["PUT"])
@login_required
def update_family_settings_route():
    """עדכון העדפות המשפחה. מקבל עדכון חלקי וממזג לתוך הקיים."""
    user = get_current_user()
    if not user["family_id"]:
        return jsonify({"error": "לא מצאנו את המשפחה שלך — רעננו את הדף, ואם זה חוזר התחברו מחדש"}), 400

    body  = request.get_json(silent=True) or {}
    patch = {}

    if isinstance(body.get("owner_attribution"), dict):
        oa = body["owner_attribution"]
        patch["owner_attribution"] = {
            k: bool(oa[k]) for k in ("expense", "income", "savings") if k in oa
        }

    if isinstance(body.get("anomaly"), dict):
        an, out = body["anomaly"], {}
        if "enabled" in an:
            out["enabled"] = bool(an["enabled"])
        try:
            if "percent" in an:
                pct = int(an["percent"])
                if not 100 <= pct <= 1000:
                    return jsonify({"error": "אחוז ההתראה חייב להיות בין 100 ל-1000"}), 422
                out["percent"] = pct
            if "min_gap" in an:
                gap = int(an["min_gap"])
                if not 0 <= gap <= 100000:
                    return jsonify({"error": "הפער המינימלי חייב להיות בין 0 ל-100,000"}), 422
                out["min_gap"] = gap
        except (TypeError, ValueError):
            return jsonify({"error": "ערכי ההתראות חייבים להיות מספרים"}), 422
        patch["anomaly"] = out

    # תקציבי קטגוריות. מגיעים מהלקוח, אז נאמתים כמו כל סכום כסף אחר,
    # ונבדקים שהם באמת קטגוריות של המשפחה הזאת.
    if isinstance(body.get("limits"), dict):
        family_categories = {c["id"] for c in db.get_categories(user["family_id"])}
        limits = dict((family_settings().get("limits") or {}))

        for cat_id, entry in body["limits"].items():
            if cat_id not in family_categories:
                return jsonify({"error": "קטגוריה לא נמצאה"}), 422

            # ‎null‎ או סכום 0 = הסרת התקציב. זו הדרך לבטל, ולא מחיקה
            # נפרדת — כך "לא להגדיר תקציב" הוא אותו מסלול כמו "להסיר".
            if entry is None:
                limits.pop(cat_id, None)
                continue
            if not isinstance(entry, dict):
                return jsonify({"error": "מבנה תקציב לא תקין"}), 422

            amount, err = _parse_amount(entry.get("amount"))
            if entry.get("amount") in (None, "", 0, "0"):
                limits.pop(cat_id, None)
                continue
            if err:
                return jsonify({"error": f"תקציב הקטגוריה: {err}"}), 422

            limits[cat_id] = {"amount": amount, "alert": bool(entry.get("alert", True))}

        # המפה המלאה, כי הסרה היא היעדרות ממנה. ‎_merge_settings‎ מחליפה
        # את ‎limits‎ במלואה ולא ממזגת אותה — ראו ‎_WHOLE_MAP_KEYS‎. לפני כן
        # היא מוזגה ב-‎.update()‎, שיכולה רק להוסיף, ולכן הסרה לא נשמרה.
        patch["limits"] = limits

    if "show_workplace" in body:
        patch["show_workplace"] = bool(body["show_workplace"])

    if not patch:
        return jsonify({"error": "לא התקבלו הגדרות לעדכון"}), 422

    if not db.update_family_settings(user["family_id"], patch):
        return jsonify({"error": "שמירת ההעדפות נכשלה"}), 500
    return jsonify({"status": "ok", "settings": db.get_family_settings(user["family_id"])})


@app.route("/api/family", methods=["PUT"])
@login_required
def update_family():
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    name = body.get("name", "").strip()
    if not name:
        return jsonify({"error": "נא להזין שם"}), 422
    ok = db.update_family_name(user["family_id"], name)
    return jsonify({"status": "ok" if ok else "error"})


def _user_message(err, fallback: str = "הפעולה נכשלה — נסו שוב") -> str:
    """מחזיר הודעה שמתאימה להצגה למשתמש.

    שכבת ה-DB מחזירה שני סוגי מחרוזות באותו מקום: הודעות שנכתבו למשתמש
    ("רק הבעלים של הפרויקט יכול…") וסימנים פנימיים שנכתבו למפתח
    ("Database not configured", או ‎str(e)‎ גולמי מ-Supabase). המסלולים
    הציגו את שתיהן כמו שהן.

    הכלל כאן פשוט ובכוונה: הודעה למשתמש נכתבת בעברית. מחרוזת בלי עברית
    היא פנימית — היא נכנסת ללוג ולא למסך. כך גם שגיאה עתידית שתיווסף
    בשכבת ה-DB לא תדלוף לממשק בלי שאף אחד שם לב."""
    if err and re.search(r"[\u0590-\u05FF]", str(err)):
        return str(err)
    if err:
        logger.warning("internal error surfaced to a route: %s", err)
    return fallback


def _family_rpc_message(err: str) -> str:
    """מתרגם את שגיאות ה-RPC להודעה בעברית. ההודעות המקוריות באנגלית
    ומיועדות ללוג, לא למשתמש."""
    text = (err or "").lower()
    if "only the family manager" in text:
        return "רק מנהל המשפחה יכול להסיר בני משפחה"
    if "manager cannot be removed" in text:
        return "אי אפשר להסיר את מנהל המשפחה"
    if "not a member of your family" in text:
        return "המשתמש אינו חבר במשפחה שלך"
    if "leave_family to remove yourself" in text:
        return "כדי לצאת מהמשפחה השתמשו ב\"עזיבת המשפחה\""
    return "הפעולה נכשלה — נסו שוב"


@app.route("/api/family/members/<member_id>", methods=["DELETE"])
@login_required
@limiter.limit("10 per minute")
def remove_family_member_route(member_id):
    """הסרת בן משפחה. מנהל המשפחה בלבד — נאכף ב-DB.

    keep_transactions הוא בחירה של המשתמש ולא ברירת מחדל שקטה: הכסף יצא
    מהתקציב המשותף, אז "להשאיר" שומר על הסכומים החודשיים נכונים והעסקה
    מוצגת כ"משותפת". "למחוק" משנה למפרע כל סיכום חודשי שבו הוא מופיע,
    ולכן הוא חייב להיות בחירה מודעת."""
    user = get_current_user()
    if not user["family_id"]:
        return jsonify({"error": "לא משויכת משפחה לחשבון"}), 400

    body = request.get_json(silent=True) or {}
    keep = body.get("keep_transactions", True) is not False

    ok, err = db.remove_family_member(member_id, keep_transactions=keep)
    if not ok:
        return jsonify({"error": _family_rpc_message(err)}), 403
    return jsonify({"status": "ok"})


@app.route("/api/family/leave", methods=["POST"])
@login_required
@limiter.limit("10 per minute")
def leave_family_route():
    """עזיבת המשפחה. כל בן משפחה רשאי, כולל המנהל — כשהוא עוזב הניהול
    עובר לוותיק שנשאר, כדי שלא תיוותר משפחה בלי מנהל."""
    user = get_current_user()
    if not user["family_id"]:
        return jsonify({"error": "לא משויכת משפחה לחשבון"}), 400

    body = request.get_json(silent=True) or {}
    keep = body.get("keep_transactions", True) is not False

    new_family_id, err = db.leave_family(keep_transactions=keep)
    if err or not new_family_id:
        return jsonify({"error": _family_rpc_message(err)}), 400

    # ה-session נושא את המשפחה הישנה; בלי העדכון הזה כל שליפה בבקשה הבאה
    # תסונן לפי משפחה שהמשתמש כבר לא חבר בה, והאפליקציה תיראה ריקה
    session["family_id"] = new_family_id
    return jsonify({"status": "ok"})


@app.route("/api/family/invite-code", methods=["POST"])
@login_required
@limiter.limit("10 per minute")
def rotate_invite_code_route():
    """החלפת קוד ההזמנה. הקוד הישן מפסיק לעבוד מיד — זו כל המטרה."""
    user = get_current_user()
    if not user["family_id"]:
        return jsonify({"error": "לא משויכת משפחה לחשבון"}), 400

    denied = _require_manager()
    if denied:
        return denied

    code, err = db.rotate_invite_code()
    if err or not code:
        return jsonify({"error": "החלפת הקוד נכשלה — נסו שוב"}), 400
    return jsonify({"status": "ok", "invite_code": code})


@app.route("/api/family/preview", methods=["GET"])
@login_required
@limiter.limit("20 per minute")
def preview_family_code():
    """תצוגה מקדימה לפני הצטרפות — "מצטרפים למשפחת כהן?". מוגבל בקצב כדי
    שלא ישמש לסריקת קודים."""
    code = request.args.get("code", "").strip()
    if not code:
        return jsonify({"error": "נא להזין קוד הזמנה"}), 422
    name = db.family_name_for_code(code)
    if not name:
        return jsonify({"found": False}), 404
    return jsonify({"found": True, "name": name})


@app.route("/api/family/join", methods=["POST"])
@login_required
@limiter.limit("10 per minute")
def join_family():
    """הצטרפות למשפחה קיימת אחרי ההרשמה.

    עד היום רגע ההרשמה היה ההזדמנות היחידה בכל חיי המוצר להזין קוד, ומי
    שנרשם לפני שקיבל אותו נשאר תקוע במשפחה משלו בלי דרך חזרה."""
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    code = body.get("code", "").strip()
    if not code:
        return jsonify({"error": "לא הוזן קוד הזמנה"}), 422

    # מעבר למשפחה אחרת נוטש את התנועות הקיימות — הן נשארות קשורות למשפחה
    # הישנה. למשתמש חדש זה לא מזיק; למשתמש עם היסטוריה זה הרסני, ולכן
    # דורשים אישור מפורש ומחזירים את המספר כדי שה-UI יוכל להציג אותו.
    current_family = user.get("family_id")
    if current_family and not body.get("confirm"):
        try:
            existing = db.family_transaction_count(current_family)
        except db.DataUnavailable:
            # לא ידוע כמה היסטוריה תיזנח. דילוג על האישור בגלל תקלה הוא
            # בדיוק האובדן שהאישור קיים כדי למנוע, אז מבקשים אותו בכל מקרה.
            existing = None
        if existing is None or existing:
            return jsonify({
                "needs_confirm": True,
                "transaction_count": existing,
            }), 409

    family_id, err = db.join_family_by_code(code)
    if err:
        return jsonify({"error": err}), 400

    # בלי עדכון ה-session המשתמש ימשיך לראות את המשפחה הישנה עד ליציאה וכניסה
    session["family_id"] = family_id
    return jsonify({"status": "ok", "family_id": family_id})


@app.route("/privacy")
def privacy():
    """מדיניות פרטיות — ציבורית בכוונה: מי ששוקל להירשם צריך לקרוא אותה
    לפני שהוא מוסר נתונים, לא אחרי."""
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/sw.js")
def service_worker():
    """מגיש את ה-Service Worker מהשורש כדי שה-scope שלו יכסה את כל האתר
    (רישום מ-/static/ נחסם על ידי הדפדפן)."""
    return app.send_static_file("sw.js")


# ─── Health checks ────────────────────────────────────────────────────────────
#
# שתי בדיקות, כי נשאלות כאן שתי שאלות שונות:
#
#   /health     — "התהליך חי?"  זו הבדיקה של Railway, והיא מחזירה 200 כל
#                 עוד השרת עונה. אילו היא הייתה נכשלת בגלל תקלה ב-Supabase,
#                 הפריסה הבאה הייתה נחסמת בדיוק ברגע הכי גרוע — תקלה של
#                 שתי דקות במסד הייתה הופכת להשבתה ארוכה בהרבה.
#   /health/db  — "המשתמשים יכולים באמת להשתמש באפליקציה?"  זו הבדיקה
#                 שמוניטור חיצוני צריך לעקוב אחריה, והיא מחזירה 503 כשהמסד
#                 לא עונה.
#
# קודם הייתה כאן רק הראשונה, והיא החזירה "ok" קבוע — כלומר גם כשהמסד היה
# מת. מוניטור היה מדווח שהכול תקין בזמן שאף משפחה לא רואה את הכסף שלה,
# והדרך היחידה לגלות הייתה שמישהו יטרח לספר.

_HEALTH_TTL = 5.0            # שניות
_health_cache = {"at": -_HEALTH_TTL, "ok": False, "detail": ""}


def _database_health():
    """מצב המסד, עם זיכרון של חמש שניות.

    בלי הזיכרון, מוניטור תכוף (או מישהו שמחזיק F5) היה תופס worker
    לכל בדיקה — ובדיוק בזמן תקלה, כשהבדיקות מתרבות והשרת עמוס, יש
    ארבעה workers בסך הכול."""
    now = time.monotonic()
    if now - _health_cache["at"] >= _HEALTH_TTL:
        ok, detail = db.ping()
        _health_cache.update(at=now, ok=ok, detail=detail)
        if not ok:
            logger.warning("health: database unreachable (%s)", detail)
    return _health_cache["ok"], _health_cache["detail"]


@app.route("/health")
def health():
    ok, detail = _database_health()
    # תמיד 200 — אבל אומר את האמת בגוף התשובה
    return jsonify({"status": "ok", "database": "ok" if ok else detail}), 200


@app.route("/health/db")
def health_db():
    ok, detail = _database_health()
    if ok:
        return jsonify({"status": "ok", "database": "ok"}), 200
    return jsonify({"status": "degraded", "database": detail}), 503


# ─── Security headers ─────────────────────────────────────────────────────────

# Content-Security-Policy: ההגנה החזקה ביותר מפני XSS — הדפדפן מסרב להריץ
# קוד שלא הגיע מהמקורות המותרים. אפשר היה להגדיר אותה רק אחרי שכל ה-JS
# הוצא מה-HTML לקבצים: מדיניות שמתירה 'unsafe-inline' מוותרת על רוב הערך,
# כי בדיוק כך נראית הזרקת קוד.
#
# script-src הוא 'self' בלבד — Chart.js הורד מקומית במקום להיטען מ-CDN.
# ל-style-src נדרש 'unsafe-inline' כי התבניות משתמשות ב-style="..." לערכים
# מחושבים (רוחב פסי התקדמות, צבע לכל בן משפחה); זו הרפיה מקובלת ומצומצמת,
# והיא לא מאפשרת הרצת קוד.
_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    # גוגל הוסר משניהם: הפונט מתארח אצלנו, ומדיניות שמתירה מקורות שלא
    # בשימוש היא רק משטח תקיפה מיותר.
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self'",
    "img-src 'self' data: blob:",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
])

# מצב הדיווח נשלט בסביבה כדי שאפשר יהיה להריץ קודם ב-Report-Only, לראות מה
# נשבר בפרודקשן האמיתי, ורק אז לאכוף. ברירת המחדל היא אכיפה.
_CSP_REPORT_ONLY = os.environ.get("CSP_REPORT_ONLY") == "1"


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    header = ("Content-Security-Policy-Report-Only" if _CSP_REPORT_ONLY
              else "Content-Security-Policy")
    response.headers.setdefault(header, _CSP)
    if not _IS_DEV:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


# ─── Error handlers ───────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    msg = "הדף שחיפשת לא נמצא"
    if _is_api_request():
        return jsonify({"error": msg}), 404
    return render_template("error.html", code=404, message=msg), 404


@app.errorhandler(413)
def payload_too_large(e):
    return jsonify({"error": "הקובץ או הבקשה גדולים מדי (מקסימום 8MB)"}), 413


@app.errorhandler(429)
def too_many_requests(e):
    msg = "יותר מדי ניסיונות בזמן קצר — נסה שוב בעוד דקה"
    if _is_api_request():
        return jsonify({"error": msg}), 429

    # מסלולי האימות מקבלים את הטופס עצמו בחזרה, עם ההודעה מעליו.
    # error.html הוא מבוי סתום — יש בו רק "חזור לדף הראשי" — ומי שנחסם
    # הגיע לשם בדיוק כי לחץ פעמיים על "התחבר" ולא הבין למה כלום לא קרה.
    # לשלוח אותו משם לדף מת, בלי מה שהקליד, זה להעניש אותו על חוסר סבלנות.
    if request.path in ("/login", "/signup"):
        return render_template(
            "login.html", error=msg,
            active_tab="signup" if request.path == "/signup" else "login",
            remembered_identifier=_remembered_identifier(),
            # גם כאן: מי שנחסם אחרי לחיצה כפולה לא צריך להקליד הכול מחדש
            signup=_signup_form() if request.path == "/signup" else None,
        ), 429

    return render_template("error.html", code=429, message=msg), 429


@app.errorhandler(500)
def server_error(e):
    msg = "אירעה שגיאה בשרת. נסה שוב בעוד כמה רגעים."
    if _is_api_request():
        # בלי זה תקלת שרת אמיתית מגיעה למשתמש כ"שגיאת רשת", והוא מנסה
        # שוב ושוב בקשה שלעולם לא תצליח — ואנחנו לא שומעים על התקלה.
        return jsonify({"error": msg}), 500
    return render_template("error.html", code=500, message=msg), 500


# ─── Helpers ──────────────────────────────────────────────────────────────────

_HEBREW_MONTHS = [
    "", "ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
    "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"
]

def _month_label(year: int, month: int) -> str:
    """שם החודש בעברית. חודש מחוץ לטווח נחתך במקום להיכנס לאינדוקס —
    ‎_HEBREW_MONTHS[13] זרק IndexError והפיל את העמוד, ו-‎_HEBREW_MONTHS[-5]
    החזיר בשקט את אוגוסט, וזה הגרוע מבין השניים."""
    if not 1 <= month <= 12:
        month = clock.now().month
    return f"{_HEBREW_MONTHS[month]} {year}"


if __name__ == "__main__":
    debug = os.environ.get("FLASK_ENV") == "development"
    port  = int(os.environ.get("PORT", 8080))
    app.run(debug=debug, port=port)
