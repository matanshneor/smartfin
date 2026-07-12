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
        print(f"[ERROR] get_email_by_phone: {e}")
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
        print(f"[WARN] log_login_event: {e}")


def reset_transactions(family_id: str, only_user_id: str = None):
    """איפוס עסקאות: מוחק את כל עסקאות המשפחה (כולל תבניות קבועות), או —
    אם only_user_id סופק — רק את העסקאות המשויכות לאותו משתמש. כל שורה
    שנמחקת מארוכבת אוטומטית ב-owner_archive דרך הטריגר. Returns (ok, err)."""
    client = get_client()
    if not client:
        return False, "Database not configured"
    try:
        query = client.table("transactions").delete().eq("family_id", family_id)
        if only_user_id:
            query = query.eq("user_id", only_user_id)
        query.execute()
        return True, None
    except Exception as e:
        print(f"[ERROR] reset_transactions: {e}")
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
        print(f"[ERROR] delete_my_account: {e}")
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
    """Exchanges a refresh token for a fresh access token. Returns (response, error)."""
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        response = client.auth.refresh_session(refresh_token)
        return response, None
    except Exception as e:
        return None, str(e)


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
        print(f"[ERROR] update_profile: {e}")
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

        from datetime import date
        month_start = date.today().replace(day=1).isoformat()

        client.table("transactions").update({"workplace": old_workplace}) \
            .eq("user_id", user_id).eq("type", "income") \
            .in_("category_id", salary_cat_ids) \
            .is_("workplace", "null").lt("date", month_start).execute()

        client.table("transactions").update({"workplace": new_workplace}) \
            .eq("user_id", user_id).eq("type", "income") \
            .in_("category_id", salary_cat_ids) \
            .gte("date", month_start).execute()
    except Exception as e:
        print(f"[ERROR] update_workplace_history: {e}")


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


def _filter_hidden_personal_projects(rows: list, viewer_user_id: str) -> list:
    """מסנן שורות עסקה ששייכות לפרויקט אישי של בן משפחה אחר — פרטיות:
    רק בעל הפרויקט האישי רואה את העסקאות הבודדות שבו (ראה get_category_breakdown
    לאיך הן עדיין נכללות באגרגט הכללי של החודש עבור שאר בני המשפחה)."""
    if not viewer_user_id:
        return rows
    return [
        row for row in rows
        if not row.get("projects") or not row["projects"].get("owner_id")
           or row["projects"]["owner_id"] == viewer_user_id
    ]


def get_recent_transactions(family_id: str, limit: int = 5, settings: dict = None,
                            viewer_user_id: str = None) -> list:
    """Returns the most recent transactions with category and user info."""
    client = get_client()
    if not client:
        return []
    try:
        # מרווח ביטחון: אם יסוננו שורות פרטיות, עדיין נרצה להגיע ל-limit שורות גלויות
        fetch_limit = limit * 3 if viewer_user_id else limit
        result = client.table("transactions") \
            .select("*, categories(name, icon), project_categories(name, icon), profiles(name, workplace), projects(owner_id)") \
            .eq("family_id", family_id) \
            .order("date", desc=True) \
            .order("created_at", desc=True) \
            .limit(fetch_limit) \
            .execute()
        rows = _filter_hidden_personal_projects(result.data, viewer_user_id)[:limit]
        return _format_transactions(rows, settings)
    except Exception as e:
        print(f"[ERROR] get_recent_transactions: {e}")
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
            .select("*, categories(name, icon), project_categories(name, icon), profiles(name, workplace), projects(owner_id)") \
            .eq("family_id", family_id) \
            .gte("date", f"{year}-{month:02d}-01") \
            .lt("date", _next_month(year, month)) \
            .order("date", desc=True) \
            .execute()
        rows = _filter_hidden_personal_projects(result.data, viewer_user_id)
        return _format_transactions(rows, settings)
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
            .select("*, categories(name, icon), project_categories(name, icon), profiles(name, workplace)") \
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

        today = date.today()
        new_rows = []
        for t in templates:
            is_salary = t.get("type") == "income" and t.get("category_id") in salary_cat_ids
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
        print(f"[ERROR] family_has_no_transactions: {e}")
        return False


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
    except Exception:
        return []


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
        print(f"[ERROR] update_category: {e}")
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
        print(f"[ERROR] reorder_categories: {e}")
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
        print(f"[ERROR] get_projects: {e}")
        return []


def _project_totals(family_id: str) -> dict:
    """סכום כל הזמן לכל פרויקט, מפורק לפי סוג עסקה (expense/income/savings)."""
    client = get_client()
    if not client:
        return {}
    result = client.table("transactions").select("amount, type, project_id") \
        .eq("family_id", family_id).not_.is_("project_id", "null").execute()
    totals: dict = {}
    for row in result.data:
        pid = row["project_id"]
        totals.setdefault(pid, {"expense": 0.0, "income": 0.0, "savings": 0.0})
        t = row["type"]
        if t in totals[pid]:
            totals[pid][t] += float(row["amount"])
    return totals


def add_project(family_id: str, name: str, created_by: str, budget_target: float = None,
                owner_id: str = None,
                track_expense: bool = True, track_income: bool = False, track_savings: bool = False):
    client = get_client()
    if not client:
        return None, "Database not configured"
    try:
        result = client.table("projects").insert({
            "family_id": family_id, "name": name, "budget_target": budget_target,
            "owner_id": owner_id, "created_by": created_by, "track_expense": track_expense,
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
                   track_expense: bool = True,
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
            "name": name, "budget_target": budget_target,
            "track_expense": track_expense, "track_income": track_income,
            "track_savings": track_savings,
        }).eq("id", project_id).eq("family_id", family_id).execute()

        if newly_enabled:
            _seed_project_categories(project_id, family_id, newly_enabled)
        return True
    except Exception as e:
        print(f"[ERROR] update_project: {e}")
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
        print(f"[ERROR] delete_project: {e}")
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
        for t in transactions:
            if t["type"] in totals:
                totals[t["type"]] += t["amount"]

        budget = proj.get("budget_target")
        spent = totals["expense"]
        return {
            "id": proj["id"], "name": proj["name"],
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
            "transactions": transactions,
        }
    except Exception as e:
        print(f"[ERROR] get_project_detail: {e}")
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
        print(f"[ERROR] _seed_project_categories: {e}")


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
        print(f"[ERROR] get_project_categories: {e}")
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
        print(f"[ERROR] update_project_category: {e}")
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
        print(f"[ERROR] delete_project_category: {e}")
        return False


# ─── Analytics ───────────────────────────────────────────────────────────────

def get_category_breakdown(family_id: str, year: int, month: int, type_: str = "expense",
                           viewer_user_id: str = None) -> list:
    """Returns totals grouped by category for a given month and transaction type
    (expense / income / savings). Every category of the type is always included —
    months without data for a category show 0.

    עסקאות המשויכות לפרויקט מוחרגות מסכום הקטגוריה הרגילה שלהן, ומרוכזות
    בשורה נפרדת — כדי לא לנפח את הקטגוריה הרגילה בהוצאה/הכנסה/חיסכון
    חד-פעמיים וגדולים. שורת פרויקט מופיעה רק בחודשים עם פעילות בפועל (לא
    zero-fill כמו קטגוריות).

    פרטיות פרויקט אישי: אם viewer_user_id אינו הבעלים, השורה מוצגת עם תווית
    גנרית ("פרויקט <שם פרטי>" במקום שם הפרויקט האמיתי) ובלי project_id —
    כדי שבצד הלקוח היא לא תהיה קישור לחיצה לעמוד הפרויקט."""
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
            .select("amount, categories(name, icon), project_id") \
            .eq("family_id", family_id) \
            .eq("type", type_) \
            .gte("date", f"{year}-{month:02d}-01") \
            .lt("date", _next_month(year, month)) \
            .execute()

        project_totals: dict = {}
        for row in result.data:
            pid = row.get("project_id")
            if pid:
                project_totals[pid] = project_totals.get(pid, 0.0) + float(row["amount"])
                continue
            cat  = row.get("categories") or {}
            name = cat.get("name", "אחר")
            totals[name] = totals.get(name, 0) + float(row["amount"])
            icons.setdefault(name, cat.get("icon", "📦"))

        project_rows = []
        if project_totals:
            projects = client.table("projects").select("id, name, owner_id") \
                .in_("id", list(project_totals.keys())).execute().data
            member_names = {m["id"]: m["name"] for m in get_family_members(family_id)}
            for p in projects:
                pid = p["id"]
                amt = project_totals.get(pid)
                if not amt:
                    continue
                is_owner = (not p.get("owner_id")) or (p["owner_id"] == viewer_user_id)
                if is_owner:
                    label, exposed_id = f"פרויקט: {p['name']}", pid
                else:
                    owner_name = first_name(member_names.get(p["owner_id"], "משפחה"))
                    label, exposed_id = f"פרויקט {owner_name}", None
                project_rows.append({
                    "name": label, "icon": "🎯", "total": amt,
                    "is_project": True, "project_id": exposed_id,
                })

        grand_total = sum(totals.values()) + sum(project_totals.values())
        grand_total = grand_total or 1

        breakdown = [
            {
                "name": name,
                "icon": icons[name],
                "total": round(total, 2),
                "pct":  round((total / grand_total) * 100),
            }
            for name, total in totals.items()
        ] + [
            dict(pr, pct=round((pr["total"] / grand_total) * 100), total=round(pr["total"], 2))
            for pr in project_rows
        ]
        # פעילות קודם (לפי גובה — כולל שורות פרויקט), אפסים בסוף לפי א"ב
        breakdown.sort(key=lambda x: (-x["total"], x["name"]))
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

    try:
        current, history, icons = _category_history_averages(family_id, year, month)
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


def get_run_rate_forecasts(family_id: str, year: int, month: int, settings: dict = None) -> list:
    """תחזית 'קצב ריצה': משליכה את קצב ההוצאה היומי של החודש-עד-כה לסוף
    החודש, ומתריעה מראש (לפני שהחריגה קרתה בפועל) אם ההשלכה חוצה את אותו
    סף שכבר מוגדר בהעדפות המשפחה (get_anomalies). רלוונטי רק לחודש הנוכחי
    שעדיין באמצעו — לא לחודשים שהסתיימו, ולא בימים הראשונים (קצב לא יציב).
    Returns a list of {"severity": "forecast", "text": str}."""
    import calendar
    from datetime import date

    cfg = (settings or DEFAULT_FAMILY_SETTINGS).get("anomaly", {})
    if not cfg.get("enabled", True):
        return []

    today = date.today()
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
        print(f"[ERROR] get_run_rate_forecasts: {e}")

    return forecasts


def get_member_breakdown(family_id: str, year: int, month: int, type_: str = "expense") -> list:
    """Returns totals per family member for a given month and transaction type.
    נקרא רק עבור סוגים שהמשפחה הפעילה בהם שיוך (ראה get_family_settings)."""
    client = get_client()
    if not client:
        return []
    try:
        result = client.table("transactions") \
            .select("amount, user_id, profiles(name)") \
            .eq("family_id", family_id) \
            .eq("type", type_) \
            .gte("date", f"{year}-{month:02d}-01") \
            .lt("date", _next_month(year, month)) \
            .execute()

        # מקבצים לפי user_id (ולא לפי שם) כדי לשמור על הצבע הקבוע לכל בן
        # משפחה — עסקאות משותפות (user_id=NULL) מקובצות יחד תחת "משותפת".
        members: dict = {}
        for row in result.data:
            uid = row.get("user_id")
            profile = row.get("profiles")
            name = first_name(profile["name"]) if profile and profile.get("name") else "משותפת"
            key = uid or "__shared__"
            if key not in members:
                members[key] = {"user_id": uid, "name": name, "expense": 0.0}
            members[key]["expense"] += float(row["amount"])

        return sorted(members.values(), key=lambda x: x["expense"], reverse=True)
    except Exception as e:
        print(f"[ERROR] get_member_breakdown: {e}")
        return []


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
        print(f"[ERROR] get_family_members: {e}")
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
        return True
    except Exception as e:
        print(f"[ERROR] update_family_name: {e}")
        return False


def _fetch_family(family_id: str) -> dict:
    client = get_client()
    if not client:
        return {}
    try:
        result = client.table("families").select("*").eq("id", family_id).single().execute()
        return result.data or {}
    except Exception:
        return {}


def get_family(family_id: str) -> dict:
    """ממוטב-לבקשה (ראה _request_cache) — נקרא גם ישירות וגם דרך ההעדפות."""
    return _request_cache(f"family:{family_id}", lambda: _fetch_family(family_id))


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
        # עסקה המשויכת לפרויקט משתמשת בקטגוריה הייעודית שלו (project_categories),
        # לא בקטגוריות הרגילות של המשפחה
        if row.get("project_category_id"):
            cat = row.get("project_categories") or {}
        else:
            cat = row.get("categories") or {}
        user = row.get("profiles") or {}
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
            "has_receipt":          bool(row.get("receipt_path")),
        })
    return out
