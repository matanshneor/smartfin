"""
בדיקות לרענון שאחרי מחיקת עסקה.

המחיקה מסירה את השורה מיד ומציגה "בטל" לשש שניות. בתום החלון הדף נטען
מחדש, כדי שהיתרה וה-KPI יתעדכנו.

הבעיה: הטעינה הזאת רצה בכפייה. משתמש שמחק עסקה שגויה ומיד פתח את
המודאל כדי להקליד את התיקון — וזה בדיוק הרצף שאדם עושה — קיבל טעינה
מחדש באמצע מילה. המודאל נסגר, וכל מה שהקליד אבד.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_JS = (Path(__file__).resolve().parent.parent
       / "frontend/static/js/transactions.js").read_text(encoding="utf-8")


def _fn(name):
    start = _JS.index(f"function {name}(")
    depth, i = 0, _JS.index("{", start)
    for j in range(i, len(_JS)):
        if _JS[j] == "{": depth += 1
        elif _JS[j] == "}":
            depth -= 1
            if depth == 0: return _JS[start:j + 1]
    raise AssertionError(name)


# ─── הלב ─────────────────────────────────────────────────────────────────────

def test_the_refresh_waits_while_something_is_being_edited():
    body = _fn("refreshAfterDelete")

    assert "somethingIsBeingEdited()" in body
    assert "refreshWhenEditingEnds = true" in body


def test_the_editing_window_counts():
    """מאז 5.10 יש רק חלון עריכה אחד — גם בדף הבית (העורך בשורה הוסר)."""
    body = _fn("somethingIsBeingEdited")

    assert "overlay.classList.contains('open')" in body


def test_the_deferred_refresh_actually_happens_when_editing_ends():
    """דחייה בלי השלמה היא יתרה שלא מתעדכנת לעולם."""
    assert "refreshIfPending();" in _fn("closeModal")

    body = _fn("refreshIfPending")
    assert "refreshWhenEditingEnds" in body and "refreshAfterDelete()" in body


def test_undoing_the_delete_cancels_the_pending_refresh():
    """שוחזרה העסקה — אין מה לרענן, ורענון היה סוגר מודאל פתוח לחינם."""
    # של המחיקה — לא ה"בטל" של העריכה (סבב 6, פריט 10), שמופיע קודם בקובץ
    block = _JS[_JS.index("label: 'ביטול'", _JS.index("function deleteWithUndo")):][:400]

    assert "refreshWhenEditingEnds = false" in block
    assert "clearTimeout(pendingDeleteReload)" in block


# ─── ומה קורה כשכן מרעננים ───────────────────────────────────────────────────

def test_it_prefers_the_soft_reload_where_the_page_allows_it():
    """רענון רך לא נוגע במודאל בכלל — הוא יושב מחוץ ל-main."""
    body = _fn("refreshAfterDelete")

    assert "main[data-soft-reload]" in body
    assert "window.softReload()" in body


def test_a_page_without_soft_reload_still_gets_its_totals_updated():
    """בקרת-נגד: הזהירות לא אמורה להשאיר יתרה ישנה על המסך."""
    assert "window.location.reload()" in _fn("refreshAfterDelete")


def test_the_six_second_undo_window_is_unchanged():
    """הדחייה נוגעת למה שקורה בסוף החלון, לא לאורכו."""
    assert re.search(r"setTimeout\(refreshAfterDelete,\s*6000\)", _JS)
