"""
בדיקות לשלושה ליקויי נגישות קטנים.

יעדי נגיעה — חיצי סידור הקטגוריות הם 30×15. אגודל נוגע באזור של ~45,
והתקן מבקש 24 לפחות. פספוס בטלפון מפעיל את החץ ההפוך או את השורה עצמה,
כלומר סידור קטגוריות הוא משחק ניחושים.

תוויות — שישה שדות בלי תווית מקושרת. קורא מסך מקריא "שדה טקסט" ותו לא.
בעורך העסקה יש טקסט "סכום (₪)" על המסך, אבל הוא לא מקושר לשדה: חזותית
תקין, ולקורא המסך שני דברים נפרדים.

זום — ב-iOS מיקוד בשדה עם פונט קטן מ-16px מזם את כל העמוד, **ולא מחזיר
אותו**. התפריט התחתון וכפתור ה-+ נשארים מחוץ למסך עד שצובטים ידנית.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_CSS  = (_ROOT / "frontend/static/css/style.css").read_text(encoding="utf-8")


def _rule(selector):
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", _CSS)
    assert m, f"לא נמצא {selector}"
    return m.group(1)


def _px(body, prop):
    m = re.search(rf"(?<![-\w]){prop}:\s*([\d.]+)px", body)
    return float(m.group(1)) if m else None


# ─── יעדי נגיעה ──────────────────────────────────────────────────────────────

def test_the_reorder_arrows_have_a_real_tap_target():
    body = _rule(".cat-move-btn::before")

    assert _px(body, "width")  >= 24, "אזור הנגיעה צר מדי"
    assert _px(body, "height") >= 24, "אזור הנגיעה נמוך מדי"


def test_the_two_arrows_grow_away_from_each_other():
    """הם צמודים אנכית. אזור סימטרי גדול היה חופף — ופספוס היה מפעיל
    את הכיוון ההפוך, מה שגרוע מלא לפגוע בכלל."""
    assert "bottom: 0" in _rule(".cat-move-up::before")
    assert "top: 0"    in _rule(".cat-move-down::before")


def test_the_arrows_themselves_did_not_grow():
    """בקרת-נגד: התיקון הוא באזור הנגיעה, לא בעיצוב. חצים גדולים היו
    דוחפים את שם הקטגוריה החוצה."""
    body = _rule(".cat-move-btn")

    assert _px(body, "width") == 30 and _px(body, "height") == 15


# ─── תוויות ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("field,label", [
    ("familyNameInput", "שם המשפחה"),
    ("joinCodeInput",   "קוד הזמנה"),
])
def test_settings_fields_have_a_label_a_screen_reader_can_read(field, label):
    html = (_ROOT / "frontend/templates/settings.html").read_text(encoding="utf-8")

    assert f'for="{field}"' in html, f"{field} ללא תווית מקושרת"
    assert label in html


def test_the_inline_editor_links_its_labels_to_its_fields():
    """הטקסט היה שם כל הזמן — פשוט לא מקושר."""
    js = (_ROOT / "frontend/static/js/transactions.js").read_text(encoding="utf-8")
    block = js[js.index("function buildInlineEditor"):][:3000]

    # ה-uid משורשר לתוך המחרוזת, אז אין גרש סוגר אחרי שם השדה
    for field in ("amount", "desc", "date"):
        assert f'for="\' + uid + \'-{field}"' in block, \
            f"התווית של {field} לא מקושרת"
        assert f'id="\' + uid + \'-{field}"' in block, \
            f"לשדה {field} אין id שהתווית מצביעה אליו"


def test_each_inline_editor_gets_its_own_ids():
    """יותר מעורך אחד נבנה בחיי העמוד. id חוזר היה מקשר תווית לשדה של
    שורה אחרת — כלומר קורא מסך שמקריא את המספר הלא נכון."""
    js = (_ROOT / "frontend/static/js/transactions.js").read_text(encoding="utf-8")

    assert "++inlineEditorSeq" in js


def test_the_visually_hidden_class_is_still_read_aloud():
    """‎display:none‎ היה מסתיר גם מקורא המסך — כלומר תווית שלא עושה כלום."""
    body = _rule(".sr-only")

    assert "display: none" not in body
    assert "clip-path" in body and "position: absolute" in body


# ─── זום ב-iOS ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("selector", [
    ".tx-search-input",
    ".category-row.editing .form-input",
])
def test_no_input_is_small_enough_to_trigger_ios_zoom(selector):
    body = _rule(selector)
    m = re.search(r"font-size:\s*([\d.]+)rem", body)

    assert m, f"{selector}: אין font-size"
    assert float(m.group(1)) >= 1.0, (
        f"{selector} הוא {m.group(1)}rem — iOS יזם ולא יחזיר"
    )


def test_zoom_is_not_disabled_as_a_shortcut():
    """הפתרון הקל היה ‎maximum-scale=1‎, וזה חוסם הגדלה גם ממי שבאמת
    צריך אותה."""
    base = (_ROOT / "frontend/templates/base.html").read_text(encoding="utf-8")

    assert "maximum-scale" not in base
    assert "user-scalable=no" not in base
