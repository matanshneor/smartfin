import os
import uuid
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


def set_auth_token(access_token: str):
    """Inject the user's JWT so RLS policies resolve auth.uid() correctly."""
    client = get_client()
    if client and access_token:
        try:
            client.postgrest.auth(access_token)
        except Exception as e:
            print(f"[WARNING] set_auth_token: {e}")


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
    """Exchanges a refresh token for a fresh access token. Returns (response, error)."""
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        response = client.auth.refresh_session(refresh_token)
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


def update_profile(user_id: str, name: str, phone: str = None, workplace: str = None):
    """Updates the current user's display name, phone and workplace."""
    client = get_client()
    if not client:
        return False
    try:
        client.table("profiles").update(
            {"name": name, "phone": phone, "workplace": workplace}
        ).eq("id", user_id).execute()
        return True
    except Exception as e:
        print(f"[ERROR] update_profile: {e}")
        return False


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
    """Creates a family and links the user to it if they don't have one.

    The families SELECT policy only allows reading a family once the user's
    profile already points to it — a chicken-and-egg problem for a brand-new
    family. We generate the id client-side and insert with returning="minimal"
    so Postgres never re-checks the SELECT policy on the just-inserted row.
    """
    client = get_client()
    if not client:
        return None
    try:
        profile = get_profile(user_id)
        if profile and profile.get("family_id"):
            return profile["family_id"]

        family_id = str(uuid.uuid4())
        client.table("families").insert(
            {"id": family_id, "name": family_name}, returning="minimal"
        ).execute()

        client.table("profiles").update({"family_id": family_id}).eq("id", user_id).execute()
        return family_id
    except Exception as e:
        print(f"[ERROR] ensure_family: {e}")
        return None


# ─── Family settings (העדפות משפחה) ──────────────────────────────────────────

# ברירות המחדל = ההתנהגות ההיסטורית של האתר. משפחה עם settings ריק מקבלת
# בדיוק את מה שהיה עד היום; רק מה שהמשפחה שינתה נשמר ב-DB.
DEFAULT_FAMILY_SETTINGS = {
    "owner_attribution": {"expense": True, "income": True, "savings": False},
    "anomaly": {"enabled": True, "percent": 150, "min_gap": 300},
    "show_workplace": True,
}


def _merge_settings(base: dict, patch: dict) -> dict:
    """מיזוג ברמה אחת של עומק — מפתחות מקוננים (owner_attribution, anomaly)
    מתמזגים במקום להימחק כשמעדכנים רק חלק מהם."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
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
        return True
    except Exception as e:
        print(f"[ERROR] update_family_settings: {e}")
        return False


# ─── Receipt scanning (צילום קבלה) ────────────────────────────────────────────

RECEIPT_MONTHLY_LIMIT = 100
_RECEIPT_MEDIA_TYPES = ("image/jpeg", "image/png", "image/webp")


def receipt_scans_this_month(family_id: str) -> int:
    """כמה סריקות מוצלחות בוצעו החודש — סריקות שנכשלו לא נרשמות ולא נספרות."""
    client = get_client()
    if not client or not family_id:
        return 0
    try:
        from datetime import date
        today = date.today()
        start = f"{today.year}-{today.month:02d}-01"
        result = client.table("receipt_scans").select("id", count="exact") \
            .eq("family_id", family_id).gte("created_at", start).execute()
        return result.count or 0
    except Exception as e:
        print(f"[ERROR] receipt_scans_this_month: {e}")
        return 0


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
        print(f"[ERROR] record_receipt_scan: {e}")


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
        print(f"[ERROR] delete_receipt: {e}")


def get_transaction_receipt_path(transaction_id: str, family_id: str):
    client = get_client()
    if not client:
        return None
    try:
        result = client.table("transactions").select("receipt_path") \
            .eq("id", transaction_id).eq("family_id", family_id).single().execute()
        return (result.data or {}).get("receipt_path")
    except Exception:
        return None


def scan_receipt(image_bytes: bytes, content_type: str, category_names: list):
    """שולח תמונת קבלה ל-Claude ומחלץ סכום, בית עסק, תאריך וקטגוריה מוצעת
    מתוך קטגוריות ההוצאות של המשפחה בלבד. Returns (data_dict, error)."""
    import base64

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None, "סריקת קבלות אינה מוגדרת בשרת"

    try:
        import anthropic
    except ImportError:
        return None, "סריקת קבלות אינה זמינה כרגע"

    media_type = content_type if content_type in _RECEIPT_MEDIA_TYPES else "image/jpeg"
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    category_prop = {"type": "string", "description": "השאר ריק אם אין התאמה ברורה."}
    if category_names:
        category_prop["enum"] = category_names

    tool = {
        "name": "extract_receipt",
        "description": "מחלץ מתמונת קבלה ישראלית את הסכום, שם בית העסק, התאריך והקטגוריה המתאימה.",
        "input_schema": {
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
    }

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            tools=[tool],
            tool_choice={"type": "tool", "name": "extract_receipt"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": "זו תמונה של קבלה ישראלית. חלץ ממנה את הנתונים באמצעות הכלי."},
                ],
            }],
        )
        for block in message.content:
            if block.type == "tool_use":
                data = block.input or {}
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
        print(f"[ERROR] scan_receipt: {e}")
        return None, "שגיאה בסריקת הקבלה — נסה שוב"


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

        summary["balance"]   = summary["income"] - summary["expense"]
        # יתרת עו"ש: מה שנשאר בחשבון אחרי הוצאות והפרשות לחיסכון
        summary["remaining"] = summary["income"] - summary["expense"] - summary["savings"]
        total = summary["income"] or 1
        summary["expense_pct"] = round((summary["expense"] / total) * 100)
        return summary
    except Exception as e:
        print(f"[ERROR] get_monthly_summary: {e}")
        return _empty_summary()


def get_recent_transactions(family_id: str, limit: int = 5, settings: dict = None) -> list:
    """Returns the most recent transactions with category and user info."""
    client = get_client()
    if not client:
        return []
    try:
        result = client.table("transactions") \
            .select("*, categories(name, icon), profiles(name, workplace)") \
            .eq("family_id", family_id) \
            .order("date", desc=True) \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()
        return _format_transactions(result.data, settings)
    except Exception as e:
        print(f"[ERROR] get_recent_transactions: {e}")
        return []


def get_month_transactions(family_id: str, year: int, month: int, settings: dict = None) -> list:
    """Returns all transactions for a given month."""
    client = get_client()
    if not client:
        return []
    try:
        result = client.table("transactions") \
            .select("*, categories(name, icon), profiles(name, workplace)") \
            .eq("family_id", family_id) \
            .gte("date", f"{year}-{month:02d}-01") \
            .lt("date", _next_month(year, month)) \
            .order("date", desc=True) \
            .execute()
        return _format_transactions(result.data, settings)
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


def get_recurring_transactions(family_id: str, settings: dict = None) -> list:
    """Returns all recurring transactions for the family."""
    client = get_client()
    if not client:
        return []
    try:
        result = client.table("transactions") \
            .select("*, categories(name, icon), profiles(name, workplace)") \
            .eq("family_id", family_id) \
            .eq("is_recurring", True) \
            .order("amount", desc=True) \
            .execute()
        return _format_transactions(result.data, settings)
    except Exception as e:
        print(f"[ERROR] get_recurring_transactions: {e}")
        return []


def materialize_recurring(family_id: str) -> int:
    """משלים מופעים חסרים של עסקאות קבועות עד היום (כולל רטרואקטיבית).

    כל עסקה שסומנה כקבועה משמשת "תבנית": המופע הראשון הוא העסקה עצמה,
    ומכאן נוצרים מופעים רגילים (is_recurring=False) לפי התדירות, עד היום
    או עד תאריך הסיום. הפונקציה אידמפוטנטית — מופע שכבר קיים לא ייווצר שוב.
    Returns the number of newly created instances."""
    from datetime import date

    client = get_client()
    if not client or not family_id:
        return 0
    try:
        templates = client.table("transactions").select("*") \
            .eq("family_id", family_id).eq("is_recurring", True).execute().data
        if not templates:
            return 0

        existing = client.table("transactions") \
            .select("recurring_parent_id, date") \
            .eq("family_id", family_id) \
            .not_.is_("recurring_parent_id", "null") \
            .execute().data
        have = {(r["recurring_parent_id"], str(r["date"])) for r in existing}

        today = date.today()
        new_rows = []
        for t in templates:
            for d in _recurring_occurrences(t, today):
                if (t["id"], d.isoformat()) in have:
                    continue
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
                })

        if new_rows:
            try:
                client.table("transactions").insert(new_rows, returning="minimal").execute()
            except Exception as e:
                # כשל ייחודיות = בקשה מקבילה כבר יצרה את המופעים — תקין
                if "uq_tx_recurring_occurrence" in str(e) or "23505" in str(e):
                    return 0
                raise
        return len(new_rows)
    except Exception as e:
        print(f"[ERROR] materialize_recurring: {e}")
        return 0


def _recurring_occurrences(template: dict, until) -> list:
    """תאריכי המופעים של תבנית קבועה — אחרי תאריך המקור, עד 'until' (כולל)."""
    from datetime import date, timedelta

    start = date.fromisoformat(str(template["date"]))
    end_raw = template.get("recurring_end_date")
    end = date.fromisoformat(str(end_raw)) if end_raw else None
    freq = template.get("recurring_frequency") or "monthly_1"

    out = []
    if freq in ("monthly_1", "monthly_15"):
        day = 1 if freq == "monthly_1" else 15
        # מתחילים מחודש ההתחלה עצמו — מופע באותו חודש אחרי תאריך ההתחלה נחשב
        y, m = start.year, start.month
        while len(out) < 500:
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
        print(f"[ERROR] family_needs_onboarding: {e}")
        return False


def bulk_add_categories(family_id: str, categories: list) -> tuple:
    """Inserts multiple categories at once for a family's onboarding.
    `categories` is a list of {name, icon, type} dicts. Returns (count, error)."""
    client = get_client()
    if not client:
        return 0, "Database not configured"
    rows = [
        {"name": c["name"], "icon": c.get("icon", "📦"), "type": c["type"],
         "family_id": family_id, "is_custom": True}
        for c in categories if c.get("name") and c.get("type") in ("income", "expense", "savings")
    ]
    if not rows:
        return 0, "No valid categories provided"
    try:
        result = client.table("categories").insert(rows).execute()
        return len(result.data or []), None
    except Exception as e:
        return 0, str(e)


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
        print(f"[ERROR] update_category: {e}")
        return False


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

def get_category_breakdown(family_id: str, year: int, month: int, type_: str = "expense") -> list:
    """Returns totals grouped by category for a given month and transaction type
    (expense / income / savings). Every category of the type is always included —
    months without data for a category show 0."""
    client = get_client()
    if not client:
        return []
    try:
        # All categories of this type appear every month, even with no data
        totals: dict = {}
        icons: dict  = {}
        for cat in get_categories(family_id):
            if cat.get("type") == type_:
                totals[cat["name"]] = 0.0
                icons[cat["name"]]  = cat.get("icon", "📦")

        result = client.table("transactions") \
            .select("amount, categories(name, icon)") \
            .eq("family_id", family_id) \
            .eq("type", type_) \
            .gte("date", f"{year}-{month:02d}-01") \
            .lt("date", _next_month(year, month)) \
            .execute()

        for row in result.data:
            cat  = row.get("categories") or {}
            name = cat.get("name", "אחר")
            totals[name] = totals.get(name, 0) + float(row["amount"])
            icons.setdefault(name, cat.get("icon", "📦"))

        grand_total = sum(totals.values()) or 1
        breakdown = [
            {
                "name": name,
                "icon": icons[name],
                "total": round(total, 2),
                "pct":  round((total / grand_total) * 100),
            }
            # פעילות קודם (לפי גובה), אפסים בסוף לפי א"ב
            for name, total in sorted(totals.items(), key=lambda x: (-x[1], x[0]))
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


def get_anomalies(family_id: str, year: int, month: int, summary: dict,
                  settings: dict = None) -> list:
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

    client = get_client()
    if not client:
        return alerts
    try:
        # Current + previous 3 months of expenses, grouped by category
        start_month, start_year = month - 3, year
        while start_month <= 0:
            start_month += 12
            start_year  -= 1

        result = client.table("transactions") \
            .select("amount, date, categories(name, icon)") \
            .eq("family_id", family_id) \
            .eq("type", "expense") \
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

        for name, total in current.items():
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
        print(f"[ERROR] get_anomalies: {e}")

    return alerts


def get_member_breakdown(family_id: str, year: int, month: int, type_: str = "expense") -> list:
    """Returns totals per family member for a given month and transaction type.
    נקרא רק עבור סוגים שהמשפחה הפעילה בהם שיוך (ראה get_family_settings)."""
    client = get_client()
    if not client:
        return []
    try:
        result = client.table("transactions") \
            .select("amount, profiles(name, workplace)") \
            .eq("family_id", family_id) \
            .eq("type", type_) \
            .gte("date", f"{year}-{month:02d}-01") \
            .lt("date", _next_month(year, month)) \
            .execute()

        members: dict = {}
        for row in result.data:
            profile = row.get("profiles")
            name = first_name(profile["name"]) if profile and profile.get("name") else "משותף"
            if name not in members:
                members[name] = {"name": name, "expense": 0.0}
            members[name]["expense"] += float(row["amount"])

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
        members = result.data or []
        for m in members:
            m["full_name"] = m.get("name", "")
            m["name"] = first_name(m.get("name", ""))
        return members
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
        cat = row.get("categories") or {}
        user = row.get("profiles") or {}
        out.append({
            "id":                   row["id"],
            "type":                 row["type"],
            "amount":               float(row["amount"]),
            "description":          row.get("description") or "",
            "date":                 str(row["date"]),
            "category_id":          row.get("category_id"),
            "category_name":        cat.get("name", "אחר"),
            "category_icon":        cat.get("icon", "📦"),
            "user_id":              row.get("user_id"),
            "user_name":            first_name(user.get("name", "")) if row.get("user_id") else "משותף",
            # מיקום העבודה מוצג רק על הכנסות משכורת, ורק אם המשפחה בחרה בכך
            "workplace":            (user.get("workplace")
                                     if show_workplace and row["type"] == "income"
                                        and "משכורת" in cat.get("name", "")
                                     else None),
            "is_recurring":         row.get("is_recurring", False),
            "recurring_frequency":  row.get("recurring_frequency"),
            "recurring_end_date":   str(row["recurring_end_date"]) if row.get("recurring_end_date") else None,
            "has_receipt":          bool(row.get("receipt_path")),
        })
    return out
