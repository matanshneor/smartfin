"""התראות לטלפון — Web Push (מתן, 31.10).

חמש התראות, כולן למשפחה ולא לאדם אחד:
  · בן משפחה הצטרף           — ברגע ההצטרפות (‎app.join_*‎)
  · המשכורת נרשמה            — המשכורת הראשונה בחודש, ברגע הרישום
  · חודש נסגר                — ב-1 לחודש, בבוקר
  · תשלום אחרון              — ביום שבו יורד התשלום האחרון בסדרת תשלומים
  · לא נרשם כלום כבר שבוע    — אחרי 7, 14 ו-21 יום בלי עסקה חדשה
שלוש האחרונות נשלחות מ-‎/internal/push/daily‎, ש-‎pg_cron‎ קורא לו פעם ביום.

ההצפנה ממומשת כאן (RFC 8291, ‎aes128gcm‎) על ‎cryptography‎ שכבר בתלויות,
ולא דרך ‎pywebpush‎ — שגוררת ‎http-ece‎, חבילה שלא נבנית בכל סביבה. החתימה
מול שירות ההתראות היא VAPID (RFC 8292): ‎JWT‎ ב-ES256.

בלי ‎VAPID_PRIVATE_KEY‎ בסביבה לא נשלח כלום, בשקט — מקומית ובבדיקות.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logger = logging.getLogger(__name__)

_RECORD_SIZE = 4096
_TTL_SECONDS = 24 * 3600


# ─── מפתחות ─────────────────────────────────────────────────────────────────

def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64u_decode(text: str) -> bytes:
    text = (text or "").strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _point(public_key) -> bytes:
    return public_key.public_bytes(serialization.Encoding.X962,
                                   serialization.PublicFormat.UncompressedPoint)


def generate_vapid_keys() -> tuple:
    """‎(private, public)‎ ב-base64url — להגדרה ב-Railway פעם אחת."""
    key = ec.generate_private_key(ec.SECP256R1())
    d = key.private_numbers().private_value.to_bytes(32, "big")
    return b64u(d), b64u(_point(key.public_key()))


def _vapid_key():
    raw = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    if not raw:
        return None
    try:
        return ec.derive_private_key(int.from_bytes(b64u_decode(raw), "big"), ec.SECP256R1())
    except Exception:
        logger.error("VAPID_PRIVATE_KEY אינו מפתח תקין — התראות כבויות")
        return None


def public_key() -> str | None:
    """המפתח הציבורי, לדפדפן (‎applicationServerKey‎). ‎None‎ — התראות כבויות."""
    key = _vapid_key()
    return b64u(_point(key.public_key())) if key else None


def enabled() -> bool:
    return _vapid_key() is not None


# ─── הצפנה (RFC 8291) ──────────────────────────────────────────────────────

def _hkdf(salt: bytes, info: bytes, length: int, ikm: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypt(payload: bytes, p256dh: str, auth: str, *, _server_key=None, _salt=None) -> bytes:
    """גוף ההודעה המוצפן, בפורמט ‎aes128gcm‎ — רשומה אחת.

    ‎_server_key‎ ו-‎_salt‎ — רק לבדיקות (וקטורי הבדיקה של ה-RFC)."""
    ua_public = b64u_decode(p256dh)
    auth_secret = b64u_decode(auth)
    if len(ua_public) != 65 or len(auth_secret) < 16:
        raise ValueError("מפתחות מנוי לא תקינים")
    server_key = _server_key or ec.generate_private_key(ec.SECP256R1())
    server_public = _point(server_key.public_key())
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    shared = server_key.exchange(ec.ECDH(), ua_key)

    ikm = _hkdf(auth_secret, b"WebPush: info\x00" + ua_public + server_public, 32, shared)
    salt = _salt or os.urandom(16)
    cek = _hkdf(salt, b"Content-Encoding: aes128gcm\x00", 16, ikm)
    nonce = _hkdf(salt, b"Content-Encoding: nonce\x00", 12, ikm)
    if len(payload) + 1 + 16 > _RECORD_SIZE:
        raise ValueError("ההודעה ארוכה מדי")
    body = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    header = salt + _RECORD_SIZE.to_bytes(4, "big") + bytes([len(server_public)]) + server_public
    return header + body


# ─── VAPID (RFC 8292) ──────────────────────────────────────────────────────

def vapid_header(endpoint: str, key=None, now=None) -> str:
    key = key or _vapid_key()
    url = urlparse(endpoint)
    claims = {
        "aud": f"{url.scheme}://{url.netloc}",
        "exp": int((now or time.time()) + 12 * 3600),
        "sub": os.environ.get("VAPID_SUBJECT", "").strip() or "mailto:matanshneor1@gmail.com",
    }
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = b64u(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{head}.{body}".encode()
    r, s = decode_dss_signature(key.sign(signing_input, ec.ECDSA(hashes.SHA256())))
    token = f"{head}.{body}.{b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return f"vapid t={token}, k={b64u(_point(key.public_key()))}"


# ─── שליחה ──────────────────────────────────────────────────────────────────

def _allowed_endpoint(endpoint: str) -> bool:
    """רק לשירותי התראות אמיתיים — הכתובת מגיעה מהדפדפן, ובלי הבדיקה הזאת
    השרת היה שולח בקשות לכל כתובת שמישהו רשם (SSRF)."""
    try:
        url = urlparse(endpoint)
    except ValueError:
        return False
    host = (url.hostname or "").lower()
    return url.scheme == "https" and (
        host == "fcm.googleapis.com" or host.endswith(".push.apple.com")
        or host.endswith(".notify.windows.com") or host.endswith(".push.services.mozilla.com")
        or host == "updates.push.services.mozilla.com")


def send(subscriptions: list, message: dict) -> list:
    """שולחת לכל המנויים. מחזירה את הכתובות שכבר לא קיימות (404/410),
    כדי שהקורא ימחק אותן. כשל במנוי אחד לא עוצר את השאר."""
    key = _vapid_key()
    if not key or not subscriptions:
        return []
    payload = json.dumps(message, ensure_ascii=False).encode()
    dead = []
    with httpx.Client(timeout=10) as client:
        for sub in subscriptions:
            endpoint = sub.get("endpoint") or ""
            if not _allowed_endpoint(endpoint):
                continue
            try:
                body = encrypt(payload, sub.get("p256dh"), sub.get("auth"))
                res = client.post(endpoint, content=body, headers={
                    "Authorization": vapid_header(endpoint, key),
                    "Content-Encoding": "aes128gcm",
                    "Content-Type": "application/octet-stream",
                    "TTL": str(_TTL_SECONDS),
                    "Urgency": "normal",
                })
                if res.status_code in (404, 410):
                    dead.append(endpoint)
                elif res.status_code >= 400:
                    logger.warning("push: %s מ-%s", res.status_code, urlparse(endpoint).hostname)
            except Exception:
                logger.warning("push: שליחה נכשלה", exc_info=True)
    return dead


def send_in_background(subscriptions: list, message: dict) -> None:
    """כמו ‎notify.notify_owner‎: בלי לעכב את הבקשה, ובלי לגעת במסד מה-thread."""
    if not subscriptions or not enabled():
        return
    threading.Thread(target=send, args=(list(subscriptions), dict(message)), daemon=True).start()


# ─── הנוסחים ────────────────────────────────────────────────────────────────

from .money import format_money  # noqa: E402
from .wording import HEBREW_MONTHS  # noqa: E402


def _shekels(value) -> str:
    return "₪" + format_money(round(float(value or 0)))


def member_joined(name: str, family_name: str) -> dict:
    # בלי פועל — "הצטרף" / "הצטרפה" ניחוש של מגדר לפי שם
    return {"title": "הצטרפות למשפחה 👋",
            "body": f"{name or 'בן משפחה חדש'} עכשיו חלק מ{family_name or 'המשפחה'}",
            "url": "/settings", "tag": "member-joined"}


def salary(amount, month: int) -> dict:
    return {"title": "המשכורת נרשמה 💰",
            "body": f"משכורת של {_shekels(amount)} נרשמה ל{HEBREW_MONTHS[month]}",
            "url": "/", "tag": "salary"}


def month_closed(month: int, income, expense, savings) -> dict:
    left = float(income or 0) - float(expense or 0) - float(savings or 0)
    parts = [f"הכנסות {_shekels(income)}", f"הוצאות {_shekels(expense)}"]
    if float(savings or 0):
        parts.append(f"חיסכון {_shekels(savings)}")
    tail = f"נשארו {_shekels(left)}" if left >= 0 else f"גירעון של {_shekels(-left)}"
    return {"title": f"{HEBREW_MONTHS[month]} נסגר 📅",
            "body": " · ".join(parts) + ". " + tail,
            "url": "/months", "tag": "month-closed"}


def last_installment(description: str, amount) -> dict:
    what = (description or "").strip() or "סדרת תשלומים"
    return {"title": "תשלום אחרון 🏁",
            "body": f"{what}: היום יורד התשלום האחרון, {_shekels(amount)}. "
                    f"מהחודש הבא — {_shekels(amount)} פחות בחודש",
            "url": "/settings", "tag": "last-installment"}


def quiet_week(weeks: int) -> dict:
    span = "כבר שבוע" if weeks <= 1 else ("כבר שבועיים" if weeks == 2 else f"כבר {weeks} שבועות")
    return {"title": f"לא נרשמו עסקאות {span}",
            "body": "רוצים לייבא את החודש מחברת האשראי? זה לוקח כמה דקות",
            "url": "/import", "tag": "quiet-week"}
