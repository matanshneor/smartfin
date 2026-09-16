"""
בדיקות להודעות שמוצגות למשתמש.

15 הודעות שגיאה הוחזרו למסך באנגלית — "Missing required fields: amount,
type, date", "No family linked to account", "type must be expense, income,
or savings". הן נכתבו כהודעות למפתח, והקוד הציג אותן כמו שהן למשתמש
שהאפליקציה כולה בעברית.

השורש הוא ששכבת ה-DB מחזירה שני סוגי מחרוזות באותו מקום: הודעות שנכתבו
למשתמש, וסימנים פנימיים כמו "Database not configured" או str(e) גולמי
מ-Supabase. המסלולים הציגו את שתיהן.
"""
import ast
import re
from pathlib import Path

import pytest

from backend import app as app_module

pytestmark = pytest.mark.unit

_APP = Path(__file__).resolve().parent.parent / "backend/app.py"
_HEBREW = re.compile(r"[֐-׿]")


def _literal_error_messages():
    """כל ‎jsonify({"error": "…"})‎ עם מחרוזת קבועה."""
    tree = ast.parse(_APP.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "jsonify"):
            continue
        for arg in node.args:
            if not isinstance(arg, ast.Dict):
                continue
            for k, v in zip(arg.keys, arg.values):
                if (isinstance(k, ast.Constant) and k.value == "error"
                        and isinstance(v, ast.Constant) and isinstance(v.value, str)):
                    out.append((node.lineno, v.value))
    return out


def test_no_route_answers_the_user_in_english():
    english = [(l, m) for l, m in _literal_error_messages() if not _HEBREW.search(m)]

    assert not english, f"הודעות באנגלית למשתמש עברי: {english}"


def test_there_are_actually_messages_to_check():
    """שומר מפני בדיקה שעוברת כי היא לא מצאה כלום."""
    assert len(_literal_error_messages()) > 20


# ─── השער שמונע את הדליפה הבאה ───────────────────────────────────────────────

def test_an_internal_string_never_reaches_the_screen():
    """‎"Database not configured"‎ הוא סימן ללוג. הוא הופיע 23 פעמים
    בשכבת ה-DB, ובכמה מסלולים הוחזר למשתמש כמו שהוא."""
    assert app_module._user_message("Database not configured") == "הפעולה נכשלה — נסו שוב"


def test_a_raw_supabase_exception_never_reaches_the_screen():
    """כמה פונקציות מחזירות ‎str(e)‎ — טקסט של ספרייה, לפעמים עם פרטי
    שאילתה בתוכו."""
    msg = app_module._user_message("APIError: {'code': 'PGRST116', 'details': ...}")

    assert msg == "הפעולה נכשלה — נסו שוב"


def test_a_message_written_for_the_user_passes_through():
    """בקרת-נגד: השער לא אמור לבלוע הודעות טובות."""
    real = "רק הבעלים של הפרויקט יכול להפוך אותו למשותף"

    assert app_module._user_message(real) == real


def test_the_caller_can_choose_its_own_fallback():
    assert app_module._user_message(None, "עדכון הסיסמה נכשל") == "עדכון הסיסמה נכשל"


def test_a_leaked_internal_string_is_logged_so_it_can_be_fixed(caplog):
    """בליעה שקטה הייתה מחליפה באג אחד באחר."""
    import logging
    with caplog.at_level(logging.WARNING):
        app_module._user_message("Database not configured")

    assert any("internal error" in r.message for r in caplog.records)
