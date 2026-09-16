"""
בדיקות להסתרה אמיתית של שכבות-על.

המודאל ודיאלוג האישור הוסתרו ב-‎opacity: 0‎ בלבד. שקיפות מסתירה מהעין —
לא מהמקלדת ולא מקורא המסך. שניהם יושבים ב-base.html, כלומר בכל עמוד
באפליקציה, ולכן:

· לחיצה על Tab מעבר לתפריט התחתון העבירה את המיקוד לתוך טופס העסקה
  הבלתי נראה, לכ-15 לחיצות, עם טבעת מיקוד שאי אפשר לראות.
· VoiceOver הקריא את כל טופס העסקה בכל מסך — "הוספת עסקה, הוצאה,
  הכנסה, חיסכון, סכום בשקלים…" — לפני התוכן האמיתי של העמוד.

כלומר האפליקציה לא הייתה שמישה עם קורא מסך.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_CSS  = (_ROOT / "frontend/static/css/style.css").read_text(encoding="utf-8")


def _rule(selector):
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", _CSS)
    assert m, f"לא נמצא הכלל {selector}"
    return m.group(1)


# ─── ההסתרה ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("selector,what", [
    (".modal-overlay",   "טופס העסקה המלא, כ-15 פקדים"),
    (".confirm-overlay", "דיאלוג אישור עם שני כפתורים"),
])
def test_a_closed_overlay_is_out_of_the_tab_order_and_the_screen_reader(selector, what):
    body = _rule(selector)

    assert "visibility: hidden" in body, (
        f"{selector} מוסתר בשקיפות בלבד — {what} נשארים נגישים למקלדת "
        "ולקורא המסך בכל עמוד"
    )


@pytest.mark.parametrize("selector", [".modal-overlay", ".confirm-overlay"])
def test_an_open_overlay_comes_back(selector):
    """בקרת-נגד: הסתרה שלא מתבטלת היא מודאל שלא נפתח."""
    assert "visibility: visible" in _rule(selector + ".open")


@pytest.mark.parametrize("selector", [".modal-overlay", ".confirm-overlay"])
def test_the_fade_out_still_looks_right(selector):
    """‎visibility‎ מתחלף בקפיצה, ולכן חייב להיות במעבר — אחרת השכבה
    נעלמת מיידית במקום להיעלם בהדרגה."""
    assert re.search(r"transition:\s*opacity[^;]*visibility", _rule(selector))


# ─── מה שההסתרה הייתה שוברת ──────────────────────────────────────────────────

@pytest.mark.parametrize("path,fn", [
    ("frontend/static/js/transactions.js", "openModal"),
    ("frontend/static/js/core.js",         "appConfirm"),
])
def test_focus_waits_for_the_element_to_become_visible(path, fn):
    """אי אפשר למקד אלמנט בתוך אב מוסתר. מיקוד באותו פריים שבו נוספה
    המחלקה נבלע בשקט — המודאל נפתח בלי מקלדת, והדיאלוג בלי מיקוד."""
    js = (_ROOT / path).read_text(encoding="utf-8")
    block = js[js.index(fn):][:1400]

    assert "requestAnimationFrame" in block, f"{fn} ממקד לפני שההסתרה התבטלה"


# ─── מה שנשאר בכוונה ─────────────────────────────────────────────────────────

def test_the_toast_stays_in_the_accessibility_tree():
    """הוא ‎role="status" aria-live="polite"‎ — אזור חי חייב להישאר בעץ
    כדי שהכרזה תישמע. הוא ריק כשהוא לא מוצג, אז אין מה להקריא, ואין בו
    שום דבר שניתן למיקוד."""
    assert "visibility: hidden" not in _rule(".toast")

    base = (_ROOT / "frontend/templates/base.html").read_text(encoding="utf-8")
    assert 'id="appToast" role="status" aria-live="polite"' in base
