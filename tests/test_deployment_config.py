"""
בדיקות להגדרת ההרצה.

השרת רץ בשני workers סינכרוניים, כלומר שתי בקשות במקביל לכל היותר.
סריקת קבלה חוסמת worker לכל משך הקריאה ל-OpenAI — 2 עד 6 שניות — אז
שתי סריקות בו-זמנית משביתות את האתר לכל שאר המשתמשים. לא מאטות: משביתות.

הבדיקה השנייה כאן חשובה יותר מהראשונה. ההרחבה המתבקשת היא ‎--threads‎
או gevent, והיא תגרום לדליפת נתונים בין משפחות: לקוח ה-Supabase הוא
סינגלטון ברמת התהליך, ו-set_auth_token משנה את כותרת ההרשאה שלו גלובלית
בכל בקשה. עם worker סינכרוני זה בטוח כי הוא מטפל בבקשה אחת בכל רגע; עם
חוטים, הבקשה של משתמש אחד רצה עם הטוקן של אחר.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_PROCFILE = (_ROOT / "Procfile").read_text(encoding="utf-8")
_WEB = next(l for l in _PROCFILE.split("\n") if l.startswith("web:"))


def test_there_is_room_for_more_than_two_concurrent_requests():
    m = re.search(r"--workers\s+(\d+)", _WEB)

    assert m, "אין --workers מפורש"
    assert int(m.group(1)) >= 4, f"{m.group(1)} workers — שתי סריקות קבלה משביתות את האתר"


def test_the_workers_are_processes_and_not_threads():
    """הבדיקה המרכזית. ההרחבה הזאת נראית מתבקשת ותגרום למשפחה אחת
    לראות את הכספים של אחרת."""
    assert "--threads" not in _WEB, (
        "חוטים על לקוח Supabase משותף = הבקשה של משתמש אחד רצה עם הטוקן של אחר"
    )
    for klass in ("gevent", "eventlet", "gthread", "tornado"):
        assert klass not in _WEB, f"worker אסינכרוני ({klass}) — אותה בעיה"


def test_the_reason_is_written_down_where_someone_would_change_it():
    """הערה בקובץ אחר לא תיקרא על ידי מי שבא להגדיל תפוקה."""
    assert "--threads" in _PROCFILE and "gevent" in _PROCFILE, "האזהרה לא כתובה"
    assert "supabase" in _PROCFILE.lower()
    assert "flask.g" in _PROCFILE, "לא נאמר מה צריך לקרות כדי שחוטים ייעשו בטוחים"


def test_the_app_is_loaded_once_and_shared():
    """בלי preload כל worker טוען את האפליקציה מחדש (~60MB לכל אחד),
    וארבעה היו עולים כמעט כפול משניים."""
    assert "--preload" in _WEB


def test_the_singleton_that_makes_threads_unsafe_still_exists():
    """אם הלקוח יהפוך יום אחד לכל-בקשה, האזהרה בטלה — והבדיקה הזאת
    תיפול ותזכיר לעדכן אותה, במקום להשאיר אזהרה שגויה לנצח."""
    db = (_ROOT / "backend/supabase_config.py").read_text(encoding="utf-8")

    assert re.search(r"^_client\s*=\s*None", db, re.M), (
        "הלקוח כבר לא סינגלטון — אפשר לשקול חוטים, ולעדכן את ההערה ב-Procfile"
    )
    assert "def set_auth_token" in db
