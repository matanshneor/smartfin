import os
from dotenv import load_dotenv

load_dotenv()

_client = None


def get_client():
    global _client
    if _client is not None:
        return _client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        print("[WARNING] SUPABASE_URL or SUPABASE_KEY not set — running without database")
        return None

    try:
        from supabase import create_client
        _client = create_client(url, key)
        return _client
    except Exception as e:
        print(f"[WARNING] Failed to connect to Supabase: {e}")
        return None


# ─── Auth ─────────────────────────────────────────────────────────────────────

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


def sign_up(email: str, password: str, name: str):
    """Returns (user_data, error_message)."""
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        response = client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"name": name}}
        })
        return response, None
    except Exception as e:
        return None, str(e)


def sign_out(access_token: str):
    client = get_client()
    if not client:
        return
    try:
        client.auth.sign_out()
    except Exception:
        pass


# ─── Profile ──────────────────────────────────────────────────────────────────

def get_profile(user_id: str):
    client = get_client()
    if not client:
        return None
    try:
        result = client.table("profiles").select("*, families(name)").eq("id", user_id).single().execute()
        return result.data
    except Exception:
        return None


def ensure_family(user_id: str, family_name: str = "המשפחה שלי"):
    """Creates a family and links the user to it if they don't have one."""
    client = get_client()
    if not client:
        return None
    try:
        profile = get_profile(user_id)
        if profile and profile.get("family_id"):
            return profile["family_id"]

        family = client.table("families").insert({"name": family_name}).execute()
        family_id = family.data[0]["id"]

        client.table("profiles").update({"family_id": family_id}).eq("id", user_id).execute()
        return family_id
    except Exception as e:
        print(f"[ERROR] ensure_family: {e}")
        return None


# ─── Transactions ─────────────────────────────────────────────────────────────

def get_monthly_summary(family_id: str, year: int, month: int) -> dict:
    """Returns totals for income, expense, savings for a given month."""
    client = get_client()
    if not client:
        return _empty_summary()
    try:
        result = client.table("transactions") \
            .select("type, amount") \
            .eq("family_id", family_id) \
            .gte("date", f"{year}-{month:02d}-01") \
            .lt("date", _next_month(year, month)) \
            .execute()

        summary = _empty_summary()
        for row in result.data:
            t = row["type"]
            if t in summary:
                summary[t] += float(row["amount"])

        summary["balance"] = summary["income"] - summary["expense"]
        total = summary["income"] or 1
        summary["expense_pct"] = round((summary["expense"] / total) * 100)
        return summary
    except Exception as e:
        print(f"[ERROR] get_monthly_summary: {e}")
        return _empty_summary()


def get_recent_transactions(family_id: str, limit: int = 5) -> list:
    """Returns the most recent transactions with category and user info."""
    client = get_client()
    if not client:
        return []
    try:
        result = client.table("transactions") \
            .select("*, categories(name, icon), profiles(name)") \
            .eq("family_id", family_id) \
            .order("date", desc=True) \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()
        return _format_transactions(result.data)
    except Exception as e:
        print(f"[ERROR] get_recent_transactions: {e}")
        return []


def get_month_transactions(family_id: str, year: int, month: int) -> list:
    """Returns all transactions for a given month."""
    client = get_client()
    if not client:
        return []
    try:
        result = client.table("transactions") \
            .select("*, categories(name, icon), profiles(name)") \
            .eq("family_id", family_id) \
            .gte("date", f"{year}-{month:02d}-01") \
            .lt("date", _next_month(year, month)) \
            .order("date", desc=True) \
            .execute()
        return _format_transactions(result.data)
    except Exception as e:
        print(f"[ERROR] get_month_transactions: {e}")
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


def delete_transaction(transaction_id: str, family_id: str):
    client = get_client()
    if not client:
        return False
    try:
        client.table("transactions") \
            .delete() \
            .eq("id", transaction_id) \
            .eq("family_id", family_id) \
            .execute()
        return True
    except Exception:
        return False


# ─── Categories ───────────────────────────────────────────────────────────────

def get_categories(family_id: str = None) -> list:
    client = get_client()
    if not client:
        return []
    try:
        query = client.table("categories").select("*")
        if family_id:
            query = query.or_(f"family_id.is.null,family_id.eq.{family_id}")
        else:
            query = query.is_("family_id", "null")
        return query.order("name").execute().data
    except Exception:
        return []


def add_custom_category(family_id: str, name: str, icon: str, type_: str):
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        result = client.table("categories").insert({
            "name": name, "icon": icon, "type": type_,
            "family_id": family_id, "is_custom": True
        }).execute()
        return result.data[0] if result.data else None, None
    except Exception as e:
        return None, str(e)


# ─── Analytics ───────────────────────────────────────────────────────────────

def get_category_breakdown(family_id: str, year: int, month: int) -> list:
    """Returns expense totals grouped by category for a given month."""
    client = get_client()
    if not client:
        return []
    try:
        result = client.table("transactions") \
            .select("amount, categories(name, icon)") \
            .eq("family_id", family_id) \
            .eq("type", "expense") \
            .gte("date", f"{year}-{month:02d}-01") \
            .lt("date", _next_month(year, month)) \
            .execute()

        totals: dict = {}
        icons: dict  = {}
        for row in result.data:
            cat  = row.get("categories") or {}
            name = cat.get("name", "אחר")
            icon = cat.get("icon", "📦")
            totals[name] = totals.get(name, 0) + float(row["amount"])
            icons[name]  = icon

        grand_total = sum(totals.values()) or 1
        breakdown = [
            {
                "name": name,
                "icon": icons[name],
                "total": round(total, 2),
                "pct":  round((total / grand_total) * 100),
            }
            for name, total in sorted(totals.items(), key=lambda x: x[1], reverse=True)
        ]
        return breakdown
    except Exception as e:
        print(f"[ERROR] get_category_breakdown: {e}")
        return []


def get_monthly_trend(family_id: str, num_months: int = 6) -> list:
    """Returns income/expense/savings totals for the last N months."""
    from datetime import date
    client = get_client()
    if not client:
        return []
    try:
        today  = date.today()
        # Calculate start date (first day of N months ago)
        start_month = today.month - num_months + 1
        start_year  = today.year
        while start_month <= 0:
            start_month += 12
            start_year  -= 1
        start_date = f"{start_year}-{start_month:02d}-01"

        result = client.table("transactions") \
            .select("type, amount, date") \
            .eq("family_id", family_id) \
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
        print(f"[ERROR] get_monthly_trend: {e}")
        return []


def get_member_breakdown(family_id: str, year: int, month: int) -> list:
    """Returns expense/income totals per family member for a given month."""
    client = get_client()
    if not client:
        return []
    try:
        result = client.table("transactions") \
            .select("type, amount, profiles(name)") \
            .eq("family_id", family_id) \
            .gte("date", f"{year}-{month:02d}-01") \
            .lt("date", _next_month(year, month)) \
            .execute()

        members: dict = {}
        for row in result.data:
            name = (row.get("profiles") or {}).get("name", "לא ידוע")
            if name not in members:
                members[name] = {"name": name, "expense": 0.0, "income": 0.0, "savings": 0.0}
            t = row["type"]
            if t in members[name]:
                members[name][t] += float(row["amount"])

        return sorted(members.values(), key=lambda x: x["expense"], reverse=True)
    except Exception as e:
        print(f"[ERROR] get_member_breakdown: {e}")
        return []


# ─── Family members ───────────────────────────────────────────────────────────

def get_family_members(family_id: str) -> list:
    client = get_client()
    if not client:
        return []
    try:
        result = client.rpc("get_family_members", {"p_family_id": family_id}).execute()
        return result.data or []
    except Exception as e:
        print(f"[ERROR] get_family_members: {e}")
        return []


def update_family_name(family_id: str, name: str):
    client = get_client()
    if not client:
        return False
    try:
        client.table("families").update({"name": name}).eq("id", family_id).execute()
        return True
    except Exception as e:
        print(f"[ERROR] update_family_name: {e}")
        return False


def get_family(family_id: str) -> dict:
    client = get_client()
    if not client:
        return {}
    try:
        result = client.table("families").select("*").eq("id", family_id).single().execute()
        return result.data or {}
    except Exception:
        return {}


def join_family_by_code(user_id: str, family_id: str) -> bool:
    """Links a user to an existing family using the family's UUID as invite code."""
    client = get_client()
    if not client:
        return False
    try:
        # Verify family exists
        fam = client.table("families").select("id").eq("id", family_id).execute()
        if not fam.data:
            return False
        client.table("profiles").update({"family_id": family_id}).eq("id", user_id).execute()
        return True
    except Exception as e:
        print(f"[ERROR] join_family_by_code: {e}")
        return False


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
        print(f"[ERROR] get_months_archive: {e}")
        return []


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _empty_summary():
    return {"income": 0.0, "expense": 0.0, "savings": 0.0, "balance": 0.0, "expense_pct": 0}


def _next_month(year: int, month: int) -> str:
    if month == 12:
        return f"{year + 1}-01-01"
    return f"{year}-{month + 1:02d}-01"


def _format_transactions(rows: list) -> list:
    out = []
    for row in rows:
        cat = row.get("categories") or {}
        user = row.get("profiles") or {}
        out.append({
            "id":            row["id"],
            "type":          row["type"],
            "amount":        float(row["amount"]),
            "description":   row.get("description") or "",
            "date":          str(row["date"]),
            "category_name": cat.get("name", "אחר"),
            "category_icon": cat.get("icon", "📦"),
            "user_name":     user.get("name", ""),
            "is_recurring":  row.get("is_recurring", False),
        })
    return out
