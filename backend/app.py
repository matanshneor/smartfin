from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
from functools import wraps
from datetime import datetime
import json
import os
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


# ─── Auth helpers ─────────────────────────────────────────────────────────────

@app.before_request
def inject_auth():
    token = session.get("access_token")
    if token:
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

            session["user_id"]        = user.id
            session["user_email"]     = user.email
            session["access_token"]   = response.session.access_token
            session["user_name"]      = profile.get("name", "משתמש") if profile else "משתמש"
            session["avatar_initial"] = (profile.get("avatar_initial") or "מ") if profile else "מ"
            session["family_id"]      = profile.get("family_id") if profile else None

            # Auto-create family if user doesn't have one
            if not session["family_id"]:
                family_id = db.ensure_family(user.id)
                session["family_id"] = family_id

            return redirect(url_for("dashboard"))

    return render_template("login.html", error=error)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        invite_code = request.form.get("invite_code", "").strip()

        if not name or not email or not password:
            error = "נא למלא את כל השדות"
        elif len(password) < 6:
            error = "הסיסמה חייבת להכיל לפחות 6 תווים"
        else:
            response, err = db.sign_up(email, password, name)
            if err:
                error = "הרשמה נכשלה – האימייל כבר קיים"
            else:
                # If invite code provided, join that family after signup
                if invite_code and response and response.user:
                    db.join_family_by_code(response.user.id, invite_code)
                return render_template("login.html",
                    success="נרשמת בהצלחה! כעת ניתן להתחבר.")

    return render_template("signup.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─── Main pages ───────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    user      = get_current_user()
    now       = datetime.now()
    year      = request.args.get("year",  now.year,  type=int)
    month     = request.args.get("month", now.month, type=int)
    family_id = user["family_id"]

    summary      = db.get_monthly_summary(family_id, year, month) if family_id else db._empty_summary()
    transactions = db.get_recent_transactions(family_id) if family_id else []
    categories   = db.get_categories(family_id)

    month_label = _month_label(year, month)

    return render_template(
        "index.html",
        active_page="dashboard",
        user=user,
        summary=summary,
        transactions=transactions,
        categories=categories,
        month_label=month_label,
        year=year,
        month=month,
        now_year=now.year,
        now_month=now.month,
    )


@app.route("/months")
@login_required
def months():
    user      = get_current_user()
    archive   = db.get_months_archive(user["family_id"]) if user["family_id"] else []
    return render_template("months.html", active_page="months", user=user,
                           archive=archive, _HEBREW_MONTHS=_HEBREW_MONTHS)


@app.route("/stats")
@login_required
def stats():
    user      = get_current_user()
    now       = datetime.now()
    year      = request.args.get("year",  now.year,  type=int)
    month     = request.args.get("month", now.month, type=int)
    family_id = user["family_id"]

    category_breakdown = db.get_category_breakdown(family_id, year, month) if family_id else []
    monthly_trend      = db.get_monthly_trend(family_id, num_months=6)     if family_id else []
    member_breakdown   = db.get_member_breakdown(family_id, year, month)   if family_id else []
    summary            = db.get_monthly_summary(family_id, year, month)    if family_id else db._empty_summary()

    return render_template(
        "stats.html",
        active_page="stats",
        user=user,
        summary=summary,
        category_breakdown=category_breakdown,
        monthly_trend=monthly_trend,
        member_breakdown=member_breakdown,
        month_label=_month_label(year, month),
        year=year,
        month=month,
        # JSON for Chart.js
        trend_json=json.dumps(monthly_trend),
        breakdown_json=json.dumps(category_breakdown),
    )


@app.route("/settings")
@login_required
def settings():
    user       = get_current_user()
    family_id  = user["family_id"]
    categories = db.get_categories(family_id)
    members    = db.get_family_members(family_id) if family_id else []
    family     = db.get_family(family_id)         if family_id else {}
    return render_template(
        "settings.html",
        active_page="settings",
        user=user,
        categories=categories,
        members=members,
        family=family,
    )


# ─── API: Transactions ────────────────────────────────────────────────────────

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
        "user_id":     user["id"],
        "family_id":   user["family_id"],
        "is_recurring":         bool(body.get("is_recurring", False)),
        "recurring_frequency":  body.get("recurring_frequency"),
        "recurring_end_date":   body.get("recurring_end_date") or None,
    }

    result, err = db.add_transaction(payload)
    if err:
        return jsonify({"error": err}), 500

    return jsonify({"status": "ok", "transaction": result}), 201


@app.route("/api/transactions/<tx_id>", methods=["DELETE"])
@login_required
def delete_transaction(tx_id):
    user = get_current_user()
    ok   = db.delete_transaction(tx_id, user["family_id"])
    return jsonify({"status": "ok" if ok else "error"}), 200 if ok else 500


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
    app.run(debug=debug)
