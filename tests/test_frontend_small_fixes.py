"""חמישה תיקוני חזית, שכל אחד מהם היה שקט ובלתי נראה עד שמישהו נתקל בו.

**ג1 — קבלה שנדבקת לעסקה הלא נכונה.** ‎resetScanUI‎ לא ניקתה את
‎txReceiptPath‎, ורק ‎resetForm‎ (שרצה רק מ-‎openAddModal‎) עשתה זאת.
סריקה שננטשה השאירה נתיב בשדה, וכל עריכה אחרת שלחה אותו יחד איתה.

**ג3 — עמוד ההתחברות מציג שני טפסים.** ‎showTab‎ לא נגעה ב-‎forgotPanel‎,
אז מעבר בין לשוניות אחרי "שכחתי סיסמה" הציג טופס איפוס מעל טופס אחר.

**ג4 — ‎.zero-toggle‎ מת במקלדת.** מוכרז ‎role="button" tabindex="0"‎
וטופל ב-‎click‎ בלבד — אלמנט שאינו ‎<button>‎ לא מייצר click מ-Enter.

**ג5 — הצליל לא ניתן לכיבוי.** דלת המילוט הייתה בקוד; שום דבר לא כתב
אליה.

**ג9 — הפס בדשבורד משקר בחודש הראשון.** ‎income == 0‎ הציג "נוצלו 0%
מההכנסות" ליד מינוס אדום — בדיוק המסך הראשון של משתמש חדש.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_JS = _ROOT / "frontend/static/js"
_TPL = _ROOT / "frontend/templates"


def _read(rel):
    return (_ROOT / rel).read_text(encoding="utf-8")


def _strip_comments(js):
    """בלי זה, הערה שמסבירה למה לא עושים משהו נספרת כעשייה שלו — בדיוק
    מה שהחמיץ שלוש מהמוטציות כאן בפעם הראשונה: התיעוד של התיקון הכיל
    את אותה מילת מפתח שהבדיקה חיפשה בקוד עצמו."""
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"^\s*//.*$", "", js, flags=re.M)


# ─── ג1: הקבלה לא נדבקת לעסקה הלא נכונה ──────────────────────────────────────

def test_reset_scan_ui_clears_the_receipt_path():
    """הלב. אם זה עדיין לא קורה כאן, סריקה שננטשה מדביקה את הקובץ
    שלה לעסקה הבאה שנפתחת לעריכה."""
    js = _read("frontend/static/js/transactions.js")
    fn = js[js.index("function resetScanUI()"):]
    fn = fn[:fn.index("\n    }")]

    assert "txReceiptPath.value = ''" in fn, \
        "resetScanUI לא מנקה את txReceiptPath — קבלה תידבק לעסקה אחרת"


def test_close_modal_goes_through_reset_scan_ui():
    """בקרת-נגד: ‎closeModal‎ הוא המסלול שרץ בכל סגירה — כולל ✕ על
    סריקה — והוא חייב לקרוא לפונקציה שמנקה."""
    js = _read("frontend/static/js/transactions.js")
    fn = js[js.index("function closeModal()"):]
    fn = fn[:fn.index("\n    }")]

    assert "resetScanUI()" in fn


# ─── ג3: עמוד ההתחברות לא מציג שני טפסים ─────────────────────────────────────

def test_switching_tabs_hides_the_forgot_password_panel():
    js = _strip_comments(_read("frontend/static/js/login.js"))
    fn = js[js.index("function showTab(tab)"):]
    fn = fn[:fn.index("\n    }")]

    assert re.search(r"forgotPanel.*style\.display\s*=\s*['\"]none['\"]", fn, re.S), \
        "showTab לא סוגר את מסך שכחתי-סיסמה — שני טפסים יוצגו יחד"


# ─── ג4: .zero-toggle מגיב למקלדת ────────────────────────────────────────────

def test_zero_toggle_responds_to_the_keyboard():
    """‎role="button" tabindex="0"‎ בלי מאזין ל-Enter/Space הוא שקר
    לקורא מסך: הוא מוכרז ככפתור ולא עושה כלום."""
    js = _strip_comments(_read("frontend/static/js/month.js"))
    keydown = js[js.index("document.addEventListener('keydown'"):]
    keydown = keydown[:keydown.index("\n});") + 4]

    assert re.search(r"closest\(['\"]\.zero-toggle['\"]\)", keydown), \
        "אין קוד שמאתר .zero-toggle במטפל המקלדת"
    assert re.search(r"zero\.click\(\)", keydown), \
        "אין טיפול במקלדת ל-.zero-toggle — תחנת Tab שלא עושה כלום"


def test_zero_toggle_still_marked_as_a_button_in_the_template():
    """בקרת-נגד: אם הסימון ירד, הבדיקה למעלה תבדוק דבר שלא קיים."""
    for tpl in ("month.html",):
        html = _read(f"frontend/templates/{tpl}")
        assert 'class="zero-toggle"' in html
        block = html[html.index('class="zero-toggle"') - 40:][:120]
        assert 'role="button"' in block and 'tabindex="0"' in block


# ─── ג5: הצליל ניתן לכיבוי ────────────────────────────────────────────────────

def test_settings_has_a_control_that_writes_the_feedback_flag():
    """הדגל היה קיים בקוד הקריאה (‎core.js‎) בלי שום דבר שכותב אליו.
    בלי הבקרה הזאת זו דלת מילוט מקושטת שאף אחד לא יכול לפתוח."""
    js = _strip_comments(_read("frontend/static/js/settings.js"))

    assert "feedbackToggle" in js
    assert re.search(r"setItem\(['\"]sf_feedback_off['\"]", js), \
        "אין קוד שכותב את הדגל שהצליל נשען עליו"
    assert re.search(r"removeItem\(['\"]sf_feedback_off['\"]", js), \
        "אין דרך להדליק בחזרה — רק לכבות"


def test_the_toggle_exists_in_the_settings_template():
    html = _read("frontend/templates/settings.html")
    assert 'id="feedbackToggle"' in html


def test_the_flag_is_still_read_by_core_js():
    """בקרת-נגד: אם ‎core.js‎ הפסיק לקרוא את הדגל, המתג החדש לא עושה כלום."""
    js = _read("frontend/static/js/core.js")
    assert "sf_feedback_off" in js


# ─── ג9: הפס בדשבורד לא משקר בחודש הראשון ────────────────────────────────────

def test_the_progress_bar_does_not_render_without_income():
    """‎used_pct = 0‎ כש-‎income == 0‎ הוא ערך ברירת מחדל, לא עובדה. הפס
    לא אמור להתקיים כשאין ממה לחשב אחוז."""
    html = _read("frontend/templates/index.html")
    bar_block = html[html.index('<div class="hero-bar">') - 200:
                     html.index('<div class="hero-bar">') + 900]

    assert "summary.income > 0" in bar_block, \
        "הפס מוצג גם כש-income הוא 0 — 'נוצלו 0%' ליד מינוס אדום"


def test_a_message_explains_the_missing_bar_instead_of_showing_nothing():
    html = _read("frontend/templates/index.html")
    assert "הוסיפו הכנסה" in html
