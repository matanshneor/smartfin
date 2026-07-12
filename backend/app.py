from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g
from dotenv import load_dotenv
from functools import wraps
from datetime import datetime, timedelta
from werkzeug.middleware.proxy_fix import ProxyFix
import json
import math
import os
import re
import time
from . import supabase_config as db

load_dotenv()

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

# "זכור אותי": the session cookie survives browser restarts until the user logs out
app.permanent_session_lifetime = timedelta(days=90)

# הקשחת עוגיות: העוגייה נושאת את טוקני Supabase, אז Secure חובה בפרודקשן
# (בפיתוח מקומי על http זה היה שובר את ההתחברות — לכן מותנה).
_IS_DEV = os.environ.get("FLASK_ENV") == "development"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",   # גם הגנת CSRF בסיסית
    SESSION_COOKIE_SECURE=not _IS_DEV,
    PREFERRED_URL_SCHEME="https" if not _IS_DEV else "http",
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,  # תקרת גודל בקשה — מגן על העלאת קבלות
)

# מאחורי ה-proxy של Railway (TLS termination) — כדי ש-request.host_url יחזיר
# https בקישורי איפוס-סיסמה. לא מזיק בפיתוח מקומי.
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# הגבלת קצב על מסלולי האימות — מונע ניחוש סיסמאות וסריקת מספרי טלפון.
# אחסון in-memory (פר-worker): מספיק להגנה בסיסית על אפליקציה משפחתית.
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri="memory://",
    default_limits=[],  # רק המסלולים שמסומנים במפורש מוגבלים
)


# ─── Auth helpers ─────────────────────────────────────────────────────────────

@app.before_request
def inject_auth():
    token = session.get("access_token")
    if not token:
        return

    # Supabase JWTs expire after ~1 hour; refresh ahead of expiry so a
    # long-lived Flask session keeps working without re-login.
    expires_at = session.get("token_expires_at") or 0
    if session.get("refresh_token") and time.time() > expires_at - 120:
        response, err = db.refresh_session(session["refresh_token"])
        if not err and response and response.session:
            token = response.session.access_token
            session["access_token"]     = token
            session["refresh_token"]    = response.session.refresh_token
            session["token_expires_at"] = response.session.expires_at
        elif err:
            # Refresh token revoked/expired — force a clean re-login
            session.clear()
            return

    db.set_auth_token(token)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
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
    """family_settings זמין בכל תבנית (התגיות, המודאל וקבוצת ההעדפות תלויים בו)."""
    if "user_id" in session:
        return {"family_settings": family_settings()}
    return {"family_settings": None}


def _member_colors(family_id):
    """צבע קבוע לכל בן משפחה לפי סדר ההצטרפות (0=זהב, 1=ירקרק, 2=סגול, 3=כחול).
    משמש לתגי השם הצבעוניים על עסקאות."""
    if not family_id:
        return {}
    members = db.get_family_members(family_id)
    return {m["id"]: i % len(_OWNER_HEX) for i, m in enumerate(members)}


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

def _normalize_phone(raw: str) -> str:
    """מנרמל מספר טלפון להשוואה/שמירה עקבית — ספרות בלבד (בלי מקפים/רווחים/+)."""
    return re.sub(r"\D", "", raw or "")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password   = request.form.get("password", "")

        if "@" in identifier:
            email = identifier
        else:
            email = db.get_email_by_phone(_normalize_phone(identifier))

        response, err = db.sign_in(email, password) if email else (None, "not found")
        if err:
            error = "אימייל/טלפון או סיסמה שגויים"
        else:
            user = response.user
            # Set JWT before querying profiles (RLS requires auth.uid())
            db.set_auth_token(response.session.access_token)
            db.log_login_event()  # תיעוד כניסה פנימי (לבעל האתר)
            profile = db.get_profile(user.id)

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
                family_id = db.ensure_family(user.id)
                session["family_id"] = family_id

            return redirect(url_for("dashboard"))

    return render_template("login.html", error=error, active_tab="login")


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
                    print(f"[ERROR] signup: {err}")
                    error = "הרשמה נכשלה — נסה שוב בעוד כמה רגעים"
            else:
                # If invite code provided, join that family after signup
                if invite_code and response and response.user:
                    db.join_family_by_code(response.user.id, invite_code)
                return render_template("login.html", active_tab="login",
                    success="נרשמת בהצלחה! כעת ניתן להתחבר.")

    return render_template("login.html", error=error, active_tab="signup")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/auth/forgot", methods=["POST"])
@limiter.limit("3 per minute")
def forgot_password():
    body  = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip()
    if not email:
        return jsonify({"error": "נא להזין אימייל"}), 422

    redirect_to = request.host_url.rstrip("/") + url_for("reset_password")
    db.send_reset_email(email, redirect_to)
    # תמיד מחזירים הצלחה — לא חושפים אילו אימיילים רשומים
    return jsonify({"status": "ok"})


@app.route("/reset-password")
def reset_password():
    """עמוד קביעת סיסמה חדשה — הטוקן מגיע ב-fragment של הקישור מהמייל."""
    return render_template("reset_password.html")


@app.route("/api/auth/reset", methods=["POST"])
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
        print(f"[ERROR] reset password: {err}")
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
        return jsonify({"error": "No family linked to account"}), 400
    if not db.family_needs_onboarding(user["family_id"]):
        return jsonify({"error": "Onboarding already completed"}), 400

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
        print(f"[ERROR] onboarding bulk_add_categories: {err}")
        return jsonify({"error": "שמירת הקטגוריות נכשלה — נסה שוב"}), 500

    return jsonify({"status": "ok", "categories_created": count})


# ─── Main pages (5 עמודים: בית · החודש · השוואה · פרויקטים · הגדרות) ────────

@app.route("/")
@login_required
def dashboard():
    """דף הבית: מבט מהיר על החודש הנוכחי + הוספת עסקה."""
    user      = get_current_user()
    now       = datetime.now()
    family_id = user["family_id"]

    if family_id and db.family_needs_onboarding(family_id):
        return redirect(url_for("onboarding"))

    # השלמת מופעים של עסקאות קבועות — פעם ביום לכל משתמש
    today_str = now.strftime("%Y-%m-%d")
    if family_id and session.get("recurring_synced") != today_str:
        db.materialize_recurring(family_id)
        session["recurring_synced"] = today_str

    summary      = db.get_monthly_summary(family_id, now.year, now.month) if family_id else db._empty_summary()
    transactions = db.get_recent_transactions(family_id, settings=family_settings(), viewer_user_id=user["id"]) if family_id else []
    categories   = db.get_categories(family_id)
    is_new_family = db.family_has_no_transactions(family_id) if family_id else True

    return render_template(
        "index.html",
        active_page="dashboard",
        user=user,
        summary=summary,
        transactions=transactions,
        categories=categories,
        member_colors=_member_colors(family_id),
        month_label=_month_label(now.year, now.month),
        year=now.year,
        month=now.month,
        is_new_family=is_new_family,
    )


@app.route("/month")
@login_required
def month_view():
    """עמוד החודש: כל הנתונים והגרפים של חודש נתון (ברירת מחדל: הנוכחי)."""
    user      = get_current_user()
    now       = datetime.now()
    year      = request.args.get("year",  now.year,  type=int)
    month     = request.args.get("month", now.month, type=int)
    family_id = user["family_id"]

    settings_ = family_settings()
    summary = db.get_monthly_summary(family_id, year, month) if family_id else db._empty_summary()

    expense_breakdown = db.get_category_breakdown(family_id, year, month, "expense", user["id"]) if family_id else []
    income_breakdown  = db.get_category_breakdown(family_id, year, month, "income", user["id"])  if family_id else []
    savings_breakdown = db.get_category_breakdown(family_id, year, month, "savings", user["id"]) if family_id else []
    is_current = (year == now.year and month == now.month)
    anomalies         = db.get_anomalies(family_id, year, month, summary, settings_) if family_id else []
    if family_id and is_current:
        anomalies += db.get_run_rate_forecasts(family_id, year, month, settings_)
    month_transactions = db.get_month_transactions(family_id, year, month, settings_, user["id"]) if family_id else []

    # גרף חלוקה בין בני משפחה לכל סוג עסקה שהמשפחה הפעילה בו שיוך
    _type_labels = {"expense": "הוצאות", "income": "הכנסות", "savings": "חיסכון"}
    member_breakdowns = []
    if family_id:
        mcolors = _member_colors(family_id)
        for t in ("expense", "income", "savings"):
            if settings_["owner_attribution"].get(t):
                rows = db.get_member_breakdown(family_id, year, month, t)
                for r in rows:
                    idx = mcolors.get(r.get("user_id"))
                    r["color"] = _OWNER_HEX.get(idx, _SHARED_HEX) if idx is not None else _SHARED_HEX
                if rows:
                    member_breakdowns.append({"type": t, "label": _type_labels[t], "rows": rows})

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
        member_colors=_member_colors(family_id),
        month_label=_month_label(year, month),
        year=year,
        month=month,
        is_current=is_current,
        summary_json=json.dumps(summary),
        expense_json=json.dumps(expense_breakdown),
        income_json=json.dumps(income_breakdown),
        savings_json=json.dumps(savings_breakdown),
        members_json=json.dumps(member_breakdowns),
    )


@app.route("/months")
@login_required
def months():
    """עמוד השוואה: החודש הנוכחי מול חודשים קודמים + כניסה לכל חודש."""
    user      = get_current_user()
    family_id = user["family_id"]
    archive   = db.get_months_archive(family_id)              if family_id else []
    trend     = db.get_monthly_trend(family_id, num_months=12) if family_id else []
    now       = datetime.now()
    return render_template("months.html", active_page="months", user=user,
                           archive=archive, trend_json=json.dumps(trend),
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

    track_expense = bool(body.get("track_expense", True))
    track_income  = bool(body.get("track_income", False))
    track_savings = bool(body.get("track_savings", False))
    if not (track_expense or track_income or track_savings):
        return None, "יש לבחור לפחות סוג עסקה אחד למעקב"

    return {
        "name": name, "budget_target": budget_target,
        "track_expense": track_expense, "track_income": track_income,
        "track_savings": track_savings,
    }, None


@app.route("/api/projects", methods=["POST"])
@login_required
def add_project_route():
    user = get_current_user()
    if not user["family_id"]:
        return jsonify({"error": "No family linked to account"}), 400
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
        print(f"[ERROR] add_project route: {err}")
        return jsonify({"error": "יצירת הפרויקט נכשלה — נסה שוב"}), 500
    return jsonify(proj), 201


@app.route("/api/projects/<project_id>", methods=["PUT"])
@login_required
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
def delete_project_route(project_id):
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    delete_transactions = bool(body.get("delete_transactions"))
    ok = db.delete_project(project_id, user["family_id"], delete_transactions=delete_transactions)
    return jsonify({"status": "ok" if ok else "error"}), 200 if ok else 500


@app.route("/api/projects/<project_id>/share", methods=["PUT"])
@login_required
def share_project_route(project_id):
    """הופך פרויקט אישי למשותף. רק הבעלים הנוכחי רשאי (נאכף ב-db.share_project)."""
    user = get_current_user()
    ok, err = db.share_project(project_id, user["family_id"], user["id"])
    if not ok:
        return jsonify({"error": err}), 422
    return jsonify({"status": "ok"})


@app.route("/api/projects/<project_id>/unshare", methods=["PUT"])
@login_required
def unshare_project_route(project_id):
    """מחזיר פרויקט משותף להיות אישי. רק מי שיצר אותו במקור רשאי (נאכף ב-db.unshare_project)."""
    user = get_current_user()
    ok, err = db.unshare_project(project_id, user["family_id"], user["id"])
    if not ok:
        return jsonify({"error": err}), 422
    return jsonify({"status": "ok"})


@app.route("/api/projects", methods=["GET"])
@login_required
def list_projects_route():
    user = get_current_user()
    return jsonify(db.get_projects(user["family_id"], user["id"]) if user["family_id"] else [])


@app.route("/api/projects/<project_id>/categories", methods=["GET"])
@login_required
def list_project_categories_route(project_id):
    user = get_current_user()
    type_ = request.args.get("type")
    return jsonify(db.get_project_categories(project_id, user["family_id"], type_))


@app.route("/api/projects/<project_id>/categories", methods=["POST"])
@login_required
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
        print(f"[ERROR] add_project_category route: {err}")
        return jsonify({"error": "הוספת הקטגוריה נכשלה — נסה שוב"}), 500
    return jsonify(cat), 201


@app.route("/api/projects/<project_id>/categories/<cat_id>", methods=["PUT"])
@login_required
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
    profile   = db.get_profile(user["id"]) or {}
    full_name = profile.get("name", user["name"])
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

    old_profile = db.get_profile(user["id"]) or {}
    old_workplace = old_profile.get("workplace") or ""

    full_name = f"{first_name} {last_name}"
    ok, err = db.update_profile(user["id"], full_name, phone or None, workplace or None)
    if not ok:
        return jsonify({"error": err or "עדכון הפרטים נכשל"}), 500

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
        return jsonify({"error": err or "עדכון הסיסמה נכשל"}), 500
    return jsonify({"status": "ok"})


@app.route("/api/account/reset", methods=["POST"])
@login_required
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
    ok, err = db.reset_transactions(
        user["family_id"],
        only_user_id=user["id"] if scope == "mine" else None,
    )
    if not ok:
        return jsonify({"error": "האיפוס נכשל"}), 500
    return jsonify({"status": "ok"})


@app.route("/api/account", methods=["DELETE"])
@login_required
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
    return jsonify({"status": "ok"})


def _parse_amount(raw):
    """פרסינג בטוח של סכום עסקה: מספר סופי וחיובי בלבד.
    מחזיר (value, error) — error בעברית מוצג למשתמש כ-422."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, "הסכום חייב להיות מספר"
    if not math.isfinite(value) or value <= 0:
        return None, "הסכום חייב להיות מספר חיובי"
    return value, None


def _resolve_owner(body: dict, user: dict, tx_type: str):
    """מי הבעלים של העסקה — לפי העדפות המשפחה: סוג שהשיוך כבוי בו נשמר
    תמיד כמשפחתי (NULL), גם אם הבקשה ניסתה לשלוח בעלים.
    ערכים: uuid של בן משפחה, "shared" = משותפת (NULL), ובלי owner — המחובר."""
    if not family_settings().get("owner_attribution", {}).get(tx_type, False):
        return None
    owner = body.get("owner")
    if owner == "shared":
        return None
    if owner:
        return owner
    return user["id"]


def _apply_project_assignment(body: dict, user: dict, tx_type: str):
    """מיישם שיוך לפרויקט (אם body['project_id'] נשלח): מוודא שהפרויקט
    עוקב אחרי סוג העסקה הזה, אוכף בשרת שיוך אוטומטי לבעלים בפרויקט אישי
    (מתעלם מ-body['owner'] במקרה הזה), ומחליף את הקטגוריה הרגילה בקטגוריית
    הפרויקט הייעודית. Returns (project_id, project_category_id, category_id, user_id, error)."""
    project_id = body.get("project_id")
    if not project_id:
        return None, None, body.get("category_id"), _resolve_owner(body, user, tx_type), None

    project = db.get_project_for_transaction(project_id, user["family_id"])
    if not project:
        return None, None, None, None, "הפרויקט לא נמצא"

    track_key = {"expense": "track_expense", "income": "track_income", "savings": "track_savings"}[tx_type]
    if not project.get(track_key):
        return None, None, None, None, "הפרויקט הזה לא עוקב אחרי סוג העסקה הזה"

    owner_id = project.get("owner_id")
    user_id  = owner_id if owner_id else _resolve_owner(body, user, tx_type)
    return project_id, body.get("project_category_id"), None, user_id, None


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
        return jsonify({"error": "No family linked to account"}), 400

    body = request.get_json(silent=True) or {}

    required = ("amount", "type", "date")
    if not all(body.get(k) for k in required):
        return jsonify({"error": "Missing required fields: amount, type, date"}), 422

    tx_type = body["type"]
    if tx_type not in ("expense", "income", "savings"):
        return jsonify({"error": "type must be expense, income, or savings"}), 422

    amount, amount_err = _parse_amount(body["amount"])
    if amount_err:
        return jsonify({"error": amount_err}), 422

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
        "date":        body["date"],
        "description": body.get("description", ""),
        "category_id": category_id,
        "user_id":     owner_user_id,
        "family_id":   user["family_id"],
        "is_recurring":         bool(body.get("is_recurring", False)),
        "recurring_frequency":  body.get("recurring_frequency"),
        "recurring_end_date":   body.get("recurring_end_date") or None,
        "project_id":           project_id,
        "project_category_id":  project_category_id,
        "workplace":            workplace_snapshot,
    }
    # קבלה מצורפת אפשרית רק בהוצאות; ריק = לא נוגעים בעמודה (לא מוחקים קבלה קיימת בעריכה)
    if tx_type == "expense" and body.get("receipt_path"):
        payload["receipt_path"] = body["receipt_path"]

    result, err = db.add_transaction(payload)
    if err:
        print(f"[ERROR] add_transaction route: {err}")
        return jsonify({"error": "הוספת העסקה נכשלה — נסה שוב"}), 500

    # עסקה קבועה חדשה (גם רטרואקטיבית) — משלימים מיד את כל המופעים עד היום
    if payload["is_recurring"]:
        db.materialize_recurring(user["family_id"])

    return jsonify({"status": "ok", "transaction": result}), 201


@app.route("/api/transactions/<tx_id>", methods=["PUT"])
@login_required
def update_transaction(tx_id):
    user = get_current_user()
    if not user["family_id"]:
        return jsonify({"error": "No family linked to account"}), 400

    body = request.get_json(silent=True) or {}

    required = ("amount", "type", "date")
    if not all(body.get(k) for k in required):
        return jsonify({"error": "Missing required fields: amount, type, date"}), 422

    tx_type = body["type"]
    if tx_type not in ("expense", "income", "savings"):
        return jsonify({"error": "type must be expense, income, or savings"}), 422

    amount, amount_err = _parse_amount(body["amount"])
    if amount_err:
        return jsonify({"error": amount_err}), 422

    project_id, project_category_id, category_id, owner_user_id, proj_err = \
        _apply_project_assignment(body, user, tx_type)
    if proj_err:
        return jsonify({"error": proj_err}), 422

    payload = {
        "amount":      amount,
        "type":        tx_type,
        "date":        body["date"],
        "description": body.get("description", ""),
        "category_id": category_id,
        "user_id":     owner_user_id,
        "is_recurring":         bool(body.get("is_recurring", False)),
        "recurring_frequency":  body.get("recurring_frequency"),
        "recurring_end_date":   body.get("recurring_end_date") or None,
        "project_id":           project_id,
        "project_category_id":  project_category_id,
    }
    # קבלה מצורפת אפשרית רק בהוצאות; ריק = לא נוגעים בעמודה (לא מוחקים קבלה קיימת בעריכה)
    if tx_type == "expense" and body.get("receipt_path"):
        payload["receipt_path"] = body["receipt_path"]

    result, err = db.update_transaction(tx_id, user["family_id"], payload)
    if err:
        print(f"[ERROR] update_transaction route: {err}")
        return jsonify({"error": "עדכון העסקה נכשל — נסה שוב"}), 500

    if payload["is_recurring"]:
        db.materialize_recurring(user["family_id"])

    return jsonify({"status": "ok", "transaction": result})


@app.route("/api/transactions/<tx_id>", methods=["DELETE"])
@login_required
def delete_transaction(tx_id):
    user = get_current_user()
    receipt_path = db.get_transaction_receipt_path(tx_id, user["family_id"])
    ok = db.delete_transaction(tx_id, user["family_id"])
    if ok and receipt_path:
        db.delete_receipt(session.get("access_token"), receipt_path)
    return jsonify({"status": "ok" if ok else "error"}), 200 if ok else 500


@app.route("/api/recurring/<template_id>/sync", methods=["PUT"])
@login_required
def sync_recurring_template(template_id):
    """סנכרון חכם: מעדכן את התבנית הקבועה עצמה (לא מופע בודד), כך שרק
    מופעים עתידיים שעוד לא נוצרו ישתמשו בערך החדש."""
    user = get_current_user()
    if not user["family_id"]:
        return jsonify({"error": "No family linked to account"}), 400

    body = request.get_json(silent=True) or {}
    amount = body.get("amount")
    try:
        amount = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        return jsonify({"error": "סכום לא תקין"}), 422

    result, err = db.update_recurring_template(
        template_id, user["family_id"],
        amount=amount,
        category_id=body.get("category_id"),
        description=body.get("description"),
    )
    if err:
        print(f"[ERROR] update_recurring_template route: {err}")
        return jsonify({"error": "עדכון העסקה הקבועה נכשל — נסה שוב"}), 500
    if not result:
        return jsonify({"error": "התבנית הקבועה לא נמצאה"}), 404
    return jsonify({"status": "ok", "transaction": result})


# ─── API: Receipt scanning (צילום קבלה) ───────────────────────────────────────

@app.route("/api/receipts/scan", methods=["POST"])
@login_required
def scan_receipt_route():
    user = get_current_user()
    if not user["family_id"]:
        return jsonify({"error": "No family linked to account"}), 400

    if db.receipt_scans_this_month(user["family_id"]) >= db.RECEIPT_MONTHLY_LIMIT:
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


@app.route("/api/receipts/<tx_id>", methods=["GET"])
@login_required
def view_receipt(tx_id):
    user = get_current_user()
    path = db.get_transaction_receipt_path(tx_id, user["family_id"])
    if not path:
        return jsonify({"error": "לא נמצאה קבלה מצורפת"}), 404
    url, err = db.get_receipt_signed_url(session.get("access_token"), path)
    if err:
        print(f"[ERROR] receipt signed url: {err}")
        return jsonify({"error": "טעינת הקבלה נכשלה — נסה שוב"}), 500
    return jsonify({"url": url})


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
        print(f"[ERROR] add_category route: {err}")
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
    user   = get_current_user()
    client = db.get_client()
    if not client:
        return jsonify({"error": "DB not configured"}), 500
    try:
        client.table("categories") \
            .delete() \
            .eq("id", cat_id) \
            .eq("family_id", user["family_id"]) \
            .eq("is_custom", True) \
            .execute()
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"[ERROR] delete_category route: {e}")
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
        return jsonify({"error": "No family linked to account"}), 400

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
        return jsonify({"error": "Name required"}), 422
    ok = db.update_family_name(user["family_id"], name)
    return jsonify({"status": "ok" if ok else "error"})


@app.route("/sw.js")
def service_worker():
    """מגיש את ה-Service Worker מהשורש כדי שה-scope שלו יכסה את כל האתר
    (רישום מ-/static/ נחסם על ידי הדפדפן)."""
    return app.send_static_file("sw.js")


# ─── Health check (Railway) ───────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


# ─── Security headers ─────────────────────────────────────────────────────────

@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    if not _IS_DEV:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


# ─── Error handlers ───────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404,
                           message="הדף שחיפשת לא נמצא"), 404


@app.errorhandler(413)
def payload_too_large(e):
    return jsonify({"error": "הקובץ או הבקשה גדולים מדי (מקסימום 8MB)"}), 413


@app.errorhandler(429)
def too_many_requests(e):
    msg = "יותר מדי ניסיונות בזמן קצר — נסה שוב בעוד דקה"
    if request.path.startswith("/api/"):
        return jsonify({"error": msg}), 429
    return render_template("error.html", code=429, message=msg), 429


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500,
                           message="אירעה שגיאה בשרת. נסה שוב בעוד כמה רגעים."), 500


# ─── Helpers ──────────────────────────────────────────────────────────────────

_HEBREW_MONTHS = [
    "", "ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
    "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"
]

def _month_label(year: int, month: int) -> str:
    return f"{_HEBREW_MONTHS[month]} {year}"


if __name__ == "__main__":
    debug = os.environ.get("FLASK_ENV") == "development"
    port  = int(os.environ.get("PORT", 8080))
    app.run(debug=debug, port=port)
