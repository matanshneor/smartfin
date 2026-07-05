from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g
from dotenv import load_dotenv
from functools import wraps
from datetime import datetime, timedelta
import json
import os
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
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
# "זכור אותי": the session cookie survives browser restarts until the user logs out
app.permanent_session_lifetime = timedelta(days=90)


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
    return {m["id"]: i % 4 for i, m in enumerate(members)}


# ─── Auth routes ──────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        response, err = db.sign_in(email, password)
        if err:
            error = "אימייל או סיסמה שגויים"
        else:
            user = response.user
            # Set JWT before querying profiles (RLS requires auth.uid())
            db.set_auth_token(response.session.access_token)
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
def signup():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        first_name       = request.form.get("first_name", "").strip()
        last_name        = request.form.get("last_name", "").strip()
        email            = request.form.get("email", "").strip()
        phone            = request.form.get("phone", "").strip()
        password         = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        invite_code      = request.form.get("invite_code", "").strip()

        if not first_name or not last_name or not email or not password:
            error = "נא למלא את כל השדות"
        elif len(password) < 6:
            error = "הסיסמה חייבת להכיל לפחות 6 תווים"
        elif password != password_confirm:
            error = "הסיסמאות אינן תואמות"
        else:
            name = f"{first_name} {last_name}"
            response, err = db.sign_up(email, password, name, phone or None)
            if err:
                error = "הרשמה נכשלה – האימייל כבר קיים"
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
        return jsonify({"error": err or "האיפוס נכשל — נסה לבקש קישור חדש"}), 400
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
        return jsonify({"error": err}), 500

    return jsonify({"status": "ok", "categories_created": count})


# ─── Main pages (4 עמודים: בית · החודש · השוואה · הגדרות) ────────────────────

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
    transactions = db.get_recent_transactions(family_id, settings=family_settings()) if family_id else []
    categories   = db.get_categories(family_id)

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

    expense_breakdown = db.get_category_breakdown(family_id, year, month, "expense") if family_id else []
    income_breakdown  = db.get_category_breakdown(family_id, year, month, "income")  if family_id else []
    savings_breakdown = db.get_category_breakdown(family_id, year, month, "savings") if family_id else []
    anomalies         = db.get_anomalies(family_id, year, month, summary, settings_) if family_id else []
    month_transactions = db.get_month_transactions(family_id, year, month, settings_) if family_id else []

    # גרף חלוקה בין בני משפחה לכל סוג עסקה שהמשפחה הפעילה בו שיוך
    _type_labels = {"expense": "הוצאות", "income": "הכנסות", "savings": "חיסכון"}
    member_breakdowns = []
    if family_id:
        for t in ("expense", "income", "savings"):
            if settings_["owner_attribution"].get(t):
                rows = db.get_member_breakdown(family_id, year, month, t)
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
        is_current=(year == now.year and month == now.month),
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
    return render_template("months.html", active_page="months", user=user,
                           archive=archive, trend_json=json.dumps(trend),
                           _HEBREW_MONTHS=_HEBREW_MONTHS)


@app.route("/stats")
@login_required
def stats():
    """כתובת ישנה — מפנה לעמוד החודש."""
    return redirect(url_for("month_view"))


@app.route("/settings")
@login_required
def settings():
    user       = get_current_user()
    family_id  = user["family_id"]
    categories = db.get_categories(family_id)
    members    = db.get_family_members(family_id)       if family_id else []
    family     = db.get_family(family_id)               if family_id else {}
    recurring  = db.get_recurring_transactions(family_id, settings=family_settings()) if family_id else []
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
        account=account,
    )


@app.route("/api/profile", methods=["PUT"])
@login_required
def update_profile():
    user = get_current_user()
    body = request.get_json(silent=True) or {}
    first_name = (body.get("first_name") or "").strip()
    last_name  = (body.get("last_name") or "").strip()
    phone      = (body.get("phone") or "").strip()
    workplace  = (body.get("workplace") or "").strip()

    if not first_name or not last_name:
        return jsonify({"error": "נא למלא שם פרטי ושם משפחה"}), 422

    full_name = f"{first_name} {last_name}"
    ok = db.update_profile(user["id"], full_name, phone or None, workplace or None)
    if not ok:
        return jsonify({"error": "עדכון הפרטים נכשל"}), 500

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

    payload = {
        "amount":      float(body["amount"]),
        "type":        tx_type,
        "date":        body["date"],
        "description": body.get("description", ""),
        "category_id": body.get("category_id"),
        "user_id":     _resolve_owner(body, user, tx_type),
        "family_id":   user["family_id"],
        "is_recurring":         bool(body.get("is_recurring", False)),
        "recurring_frequency":  body.get("recurring_frequency"),
        "recurring_end_date":   body.get("recurring_end_date") or None,
    }
    # קבלה מצורפת אפשרית רק בהוצאות; ריק = לא נוגעים בעמודה (לא מוחקים קבלה קיימת בעריכה)
    if tx_type == "expense" and body.get("receipt_path"):
        payload["receipt_path"] = body["receipt_path"]

    result, err = db.add_transaction(payload)
    if err:
        return jsonify({"error": err}), 500

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

    payload = {
        "amount":      float(body["amount"]),
        "type":        tx_type,
        "date":        body["date"],
        "description": body.get("description", ""),
        "category_id": body.get("category_id"),
        "user_id":     _resolve_owner(body, user, tx_type),
        "is_recurring":         bool(body.get("is_recurring", False)),
        "recurring_frequency":  body.get("recurring_frequency"),
        "recurring_end_date":   body.get("recurring_end_date") or None,
    }
    # קבלה מצורפת אפשרית רק בהוצאות; ריק = לא נוגעים בעמודה (לא מוחקים קבלה קיימת בעריכה)
    if tx_type == "expense" and body.get("receipt_path"):
        payload["receipt_path"] = body["receipt_path"]

    result, err = db.update_transaction(tx_id, user["family_id"], payload)
    if err:
        return jsonify({"error": err}), 500

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
        return jsonify({"error": err}), 500
    return jsonify({"url": url})


# ─── API: Categories ──────────────────────────────────────────────────────────

@app.route("/api/categories", methods=["GET"])
@login_required
def get_categories():
    user = get_current_user()
    cats = db.get_categories(user["family_id"])
    return jsonify(cats)


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
        return jsonify({"error": err}), 500
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
        return jsonify({"error": str(e)}), 500


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


# ─── Error handlers ───────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404,
                           message="הדף שחיפשת לא נמצא"), 404


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
