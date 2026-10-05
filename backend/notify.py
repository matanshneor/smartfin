"""מיילי עדכון לבעל האתר (מתן, 5.10): משפחה חדשה נרשמה, מישהו הצטרף למשפחה.

נשלחים דרך Resend. בלי ‎RESEND_API_KEY‎ ו-‎OWNER_NOTIFY_EMAIL‎ בסביבה — לא
נשלח כלום, בשקט: מקומית ובבדיקות אין מפתח, וזה המצב הרצוי.

השליחה רצה ב-thread נפרד, כדי שההרשמה לא תחכה ל-Resend — וכדי שתקלה שם
(מפתח שגוי, השירות למטה) לא תיראה למשתמש. ה-thread לא נוגע במסד: כל מה
שהמייל צריך נשלף בבקשה עצמה ומועבר אליו כטקסט. הלקוח המשותף של Supabase
לא בטוח לשימוש מכמה threads (ראו ‎_run_queries‎ ב-app.py).
"""
import html
import logging
import os
import threading

import httpx

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"
# בלי דומיין מאומת, Resend שולח מ-‎onboarding@resend.dev‎ — ורק אל המייל
# שאיתו נפתח החשבון ב-Resend. למייל לבעל האתר זה בדיוק מספיק.
_DEFAULT_FROM = "SmartFin <onboarding@resend.dev>"


def notify_owner(subject: str, lines: list) -> bool:
    """שולחת לבעל האתר. מחזירה האם יצא לדרך (לא האם הגיע)."""
    key = os.environ.get("RESEND_API_KEY", "").strip()
    to = os.environ.get("OWNER_NOTIFY_EMAIL", "").strip()
    if not key or not to:
        return False
    # שורה ריקה = רווח בין חלקים (פרטי המשפחה / מי זה)
    body_html = "".join(f"<p style=\"margin:0 0 6px\">{html.escape(line)}</p>" if line
                        else "<div style=\"height:10px\"></div>" for line in lines)
    payload = {
        "from": os.environ.get("NOTIFY_FROM", "").strip() or _DEFAULT_FROM,
        "to": [to],
        "subject": subject,
        "text": "\n".join(lines),
        "html": f'<div dir="rtl" style="font-family:Arial,sans-serif;font-size:15px">{body_html}</div>',
    }
    threading.Thread(target=_send, args=(key, payload), daemon=True).start()
    return True


def _send(key: str, payload: dict) -> None:
    try:
        r = httpx.post(_RESEND_URL, json=payload, timeout=10,
                       headers={"Authorization": f"Bearer {key}"})
        if r.status_code >= 300:
            logger.warning("notify_owner: Resend %s: %s", r.status_code, r.text[:300])
    except Exception:
        logger.exception("notify_owner")
