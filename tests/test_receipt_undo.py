"""
"בטל" החזיר את העסקה — בלי הקבלה, ובלי לומר מילה.

מחיקת עסקה מוחקת את תמונת הקבלה מהאחסון מיד. זה נכון: אחרת האחסון היה
מתמלא בקבצים שאף עסקה לא מפנה אליהם. אבל חלון ה"בטל" נשאר פתוח שש
שניות אחרי זה, והשחזור שולח ‎receipt_path: null‎ במפורש — כי כתובת
לקובץ שנמחק הייתה מייצרת תג 📎 שבור.

התוצאה: המשתמש לחץ "בטל", ראה את העסקה חוזרת, והניח שהכול חזר. הקבלה
פשוט לא הייתה שם יותר, ושום דבר לא סימן את זה.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_JS   = (_ROOT / "frontend/static/js/transactions.js").read_text(encoding="utf-8")
_CSS  = (_ROOT / "frontend/static/css/style.css").read_text(encoding="utf-8")


def _block(start, length=1400):
    return _JS[_JS.index(start):][:length]


# ─── אומרים את זה, ורק כשזה נכון ────────────────────────────────────────────

def test_the_deletion_warns_that_the_receipt_is_gone():
    block = _block("function deleteWithUndo(")

    assert "ולא תחזור" in block, "המחיקה לא מזהירה שהקבלה לא תחזור"


def test_the_warning_only_appears_when_there_was_a_receipt():
    """בקרת-נגד: אזהרה על קבלה שלא הייתה מלמדת אנשים להתעלם מהודעות."""
    block = _block("function deleteWithUndo(")

    assert "querySelector('.receipt-badge')" in block, "אין בדיקה אם הייתה קבלה בכלל"
    assert re.search(r"hadReceipt\s*\n?\s*\?", block), "ההודעה אינה מותנית"


def test_the_plain_message_is_still_there_for_a_transaction_without_one():
    block = _block("function deleteWithUndo(")

    assert "'העסקה נמחקה'" in block


# ─── וגם אחרי השחזור ────────────────────────────────────────────────────────

def test_the_restore_says_what_did_not_come_back():
    """זה הרגע שבו המשתמש באמת מסתכל על התוצאה."""
    block = _block("function restoreTransaction(")

    assert "בלי הקבלה" in block


def test_the_restore_knows_whether_there_was_one():
    block = _block("function deleteWithUndo(")

    assert "hadReceipt: hadReceipt" in block, "הידיעה לא מועברת לשחזור"


def test_the_restore_still_sends_a_null_path():
    """הקובץ נמחק מהאחסון. כתובת אליו הייתה מייצרת תג 📎 שבור."""
    block = _block("function restoreTransaction(")

    assert "receipt_path:        null" in block


# ─── ההודעה חייבת להיות קריאה ───────────────────────────────────────────────

def test_a_long_message_is_not_cut_in_half():
    """‎nowrap‎ + ‎ellipsis‎ חתכו כל הודעה ארוכה מכ-30 תווים — כולל
    האזהרה הזאת, שהיא בדיוק ההודעה שאסור לאבד."""
    block = _CSS[_CSS.index(".toast .toast-msg"):][:400]

    assert "white-space: nowrap" not in block
    assert "line-clamp: 2" in block, "בלי תקרה, הודעה חריגה תמתח את הבועה"
