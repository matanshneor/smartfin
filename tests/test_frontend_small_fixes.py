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


# ─── ג2: כשל שרת בעסקה הראשונה לא מוחק את מה שהוקלד ──────────────────────────

def test_a_server_error_reopens_the_modal_when_it_was_closed_optimistically():
    """בכשל **רשת** החלון כבר נפתח מחדש; בכשל **שרת** זה פוספס באותה
    נקודה בדיוק — הענף שמטפל ב-‎data.error‎. השדות לא מתאפסים אף פעם
    (‎closeModal‎ לא נוגע בהם), אז הבעיה היחידה הייתה שאין דרך לחזור
    אליהם מלבד ה-FAB, ש-‎openAddModal‎ מנקה."""
    js = _strip_comments(_read("frontend/static/js/transactions.js"))
    err_branch = js[js.index("if (data.error) {"):]
    err_branch = err_branch[:err_branch.index("\n            }")]

    assert re.search(r"if\s*\(placeholderRow\)\s*\{[^}]*openModal\(\)", err_branch, re.S), \
        "כשל שרת לא פותח מחדש את המודאל כשהוא נסגר אופטימית"


def test_the_network_failure_path_still_reopens_too():
    """בקרת-נגד: התיקון הקודם (כשל רשת) לא נדרס. מעוגן מתחילת שרשרת
    השמירה (‎send(false)‎) כי הקובץ מכיל כמה ‎.catch‎ אחרים שאינם קשורים."""
    js = _strip_comments(_read("frontend/static/js/transactions.js"))
    chain = js[js.index("send(false)"):]
    # ‎sfNetError‎ מזהה בלי טעות את ה-catch החיצוני של שרשרת השמירה —
    # יש בקובץ כמה ‎.catch‎ פנימיים אחרים (תופעות-לוואי) שלא קשורים.
    catch_at = chain.index("sfNetError()")
    catch_branch = chain[:catch_at][chain[:catch_at].rindex(".catch(function ()"):]

    assert "openModal()" in catch_branch


# ─── ג6: אין יותר דיאלוג של הדפדפן ──────────────────────────────────────────

def test_no_javascript_file_uses_the_browsers_own_confirm():
    """האפליקציה בנתה דיאלוג משלה, והייתה קריאה אחת ל-‎confirm‎ המקומי —
    דווקא על מעבר משפחה, שמנתק אותך מכל העסקאות שלך. ב-PWA מותקן הוא
    מרונדר עם שם המארח מעליו, משמאל לימין ובלי עיצוב: הרגע שבו
    האפליקציה נראית הכי פחות כמו עצמה."""
    offenders = []
    for f in sorted(_JS.glob("*.js")):
        code = _strip_comments(f.read_text(encoding="utf-8"))
        if re.search(r"(?<![.\w])confirm\s*\(", code):
            offenders.append(f.name)

    assert not offenders, f"דיאלוג דפדפן ב: {offenders}"


def test_the_family_switch_still_asks_before_it_moves_you():
    """בקרת-נגד: החלפת הדיאלוג לא הפכה אותה לפעולה בלי אישור."""
    js = _strip_comments(_read("frontend/static/js/settings.js"))

    assert "appConfirm" in js
    assert "לעבור למשפחה אחרת?" in js


# ─── ג10: פרטים קטנים שכל אחד מהם נראה כמו באג ──────────────────────────────

@pytest.mark.parametrize("tpl", ["project_detail.html", "project_edit.html"])
def test_the_back_chevron_points_the_right_way_in_rtl(tpl):
    """קודקוד ב-x=9 פירושו חץ שמצביע שמאלה, ובעברית שמאלה היא "קדימה" —
    שני העמודים האלה השתמשו בגליף של "הבא" בשביל "חזרה"."""
    html = _read(f"frontend/templates/{tpl}")
    back = html[:html.index("</a>")]

    assert '"15 18 9 12 15 6"' not in back, "חץ ה'חזרה' מצביע קדימה"


def test_the_profile_rows_do_not_grow_emoji_on_save():
    """השרת מרנדר ‎{{ m.phone }}‎ נקי; ה-JS הוסיף "📞 " בשמירה. השורה
    השתנתה בשמירה וחזרה לעצמה ברענון — נראה כמו באג תצוגה דווקא במסך
    שכל תפקידו להיראות אמין."""
    js = _strip_comments(_read("frontend/static/js/settings.js"))

    assert "'📞 '" not in js and "'💼 '" not in js


def test_the_confirm_dialog_announces_what_it_is_asking():
    """בלי זה קורא מסך הכריז "ביטול, לחצן, דיאלוג" — כולל על "למחוק את
    החשבון לצמיתות?"."""
    html = _read("frontend/templates/base.html")
    dialog = html[html.index('id="confirmOverlay"') - 200:][:400]

    assert 'aria-labelledby="confirmTitle"' in dialog
    assert 'aria-describedby="confirmMessage"' in dialog


def test_the_copy_button_keeps_its_own_label():
    """אחרי העתקה מוצלחת התווית שוחזרה ל-'העתק קוד' בזמן שבתבנית כתוב
    'העתק הזמנה' — הכפתור שינה את שמו בשקט."""
    js = _read("frontend/static/js/onboarding.js")
    html = _read("frontend/templates/onboarding.html")

    label = re.search(r'id="copyInviteBtn"[^>]*>([^<]+)<', html).group(1).strip()
    assert f"'{label}'" in js, f"ה-JS משחזר תווית אחרת מ-{label!r}"


def test_the_signup_tab_does_not_welcome_you_back():
    """הכותרת קבועה ונשארת גם בלשונית ההרשמה: "ברוך הבא", לשון
    יחיד-זכר, למי שמעולם לא היה כאן."""
    # על התוכן המרונדר, לא על צורת התגית: הגרסה הראשונה של הבדיקה חיפשה
    # ‎<h2>ברוך הבא</h2>‎ בזמן שבמציאות יש שם ‎class‎ — כלומר היא עברה
    # בלי שהתיקון בכלל הוחל.
    html = re.sub(r"\{#.*?#\}", "", _read("frontend/templates/login.html"), flags=re.S)

    assert "ברוך הבא" not in html, "לשונית ההרשמה מקבלת בברכה מישהו שחוזר"
    assert "ברוכים הבאים" in html


def test_every_delete_chain_handles_a_dropped_connection():
    """בלי ‎.catch‎ השורה נשארת על המסך בלי שום הודעה, והמשתמש לוחץ ✕
    שוב ושוב."""
    js = _strip_comments(_read("frontend/static/js/project-edit.js"))
    block = js[js.index("/categories/' + id, { method: 'DELETE' }"):]
    block = block[:block.index("\n});")]

    assert ".catch(" in block


def test_local_storage_is_never_touched_unguarded():
    """‎core.js‎ כבר נפל ככה פעם: ב-Safari עם עוגיות חסומות הקריאה
    **זורקת**, ובשורה הראשונה של IIFE היא הורגת את כל הקובץ."""
    offenders = []
    for f in sorted(_JS.glob("*.js")):
        code = _strip_comments(f.read_text(encoding="utf-8"))
        for m in re.finditer(r"localStorage\.(getItem|setItem|removeItem)", code):
            window = code[max(0, m.start() - 260):m.start()]
            if "try" not in window:
                offenders.append(f"{f.name}:{code[:m.start()].count(chr(10)) + 1}")

    assert not offenders, f"גישה לא מוגנת ל-localStorage: {offenders}"


def test_duplicating_a_transaction_restores_the_scan_button():
    """כפתור הסריקה מוסתר במצב עריכה, ושכפול מנקה את ‎editId‎ בלי לרענן
    אותו — השורה המשוכפלת נפתחה בלי אפשרות לצלם קבלה."""
    js = _strip_comments(_read("frontend/static/js/transactions.js"))
    block = js[js.index("duplicateBtn.addEventListener"):]
    block = block[:block.index("\n    });")]

    assert "setType(" in block


def test_swipe_structure_is_built_lazily():
    """בעמוד החודש כל עסקה מופיעה פעמיים-שלוש, אז חודש של 150 עסקאות
    היה ~350 reparent סינכרוניים בטעינה — ובלי צורך, כי ‎touchstart‎
    בונה ממילא את מה שנוגעים בו."""
    js = _strip_comments(_read("frontend/static/js/transactions.js"))

    assert "querySelectorAll(ROW_SELECTOR).forEach" not in js, \
        "המבנה עדיין נבנה לכל שורה בטעינת העמוד"
