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

    assert re.search(r"if\s*\(placeholderRow\)\s*\{[^}]*reopenAfterFailure\(\)", err_branch, re.S), \
        "כשל שרת לא פותח מחדש את המודאל כשהוא נסגר אופטימית"


def test_the_network_failure_path_still_reopens_too():
    """בקרת-נגד: התיקון הקודם (כשל רשת) לא נדרס. מעוגן מתחילת שרשרת
    השמירה (‎send(false)‎) כי הקובץ מכיל כמה ‎.catch‎ אחרים שאינם קשורים."""
    import re
    js = _strip_comments(_read("frontend/static/js/transactions.js"))
    chain = js[js.index("send(false)"):]
    # העוגן היה "הקריאה הראשונה ל-‎sfNetError‎", וזה הפסיק להיות נכון
    # כש"עדכן להבא" התחיל להציג כשל רשת משלו. ה-catch החיצוני מזוהה
    # עכשיו במה שמייחד אותו: הוא מסיר את שורת הביניים ופותח את החלון.
    # ובתוכו, לפני, ענף לטופס שכבר הוחלף (הוספה רצופה) — אז "מיד אחרי" הפך ל"בתוך"
    assert re.search(r"\.catch\(function \(\) \{[\s\S]{0,400}?if \(placeholderRow\) \{\s*"
                     r"placeholderRow\.remove\(\);\s*reopenAfterFailure\(\);", chain)


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
    # מחיקת קטגוריה (משפחה ופרויקט) עוברת דרך עוזר אחד ב-core.js
    for f in ("project-edit.js", "settings.js"):
        assert "window.sfDeleteCategory(" in _read(f"frontend/static/js/{f}"), f
    js = _strip_comments(_read("frontend/static/js/core.js"))
    block = js[js.index("window.sfDeleteCategory = function"):]
    block = block[:block.index("\n    };")]

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


def test_pages_outside_the_app_shell_clear_the_iphone_status_bar():
    """‎black-translucent‎ מצייר את הדף מתחת לשעון ולאי הדינמי. המסכים
    הראשיים מפנים לו מקום; התחברות/הרשמה/פרטיות לא פינו, ו"← חזרה"
    בדף הפרטיות ישב בגובה השעון."""
    css = re.sub(r"/\*.*?\*/", "", _read("frontend/static/css/style.css"), flags=re.S)
    for selector in (".auth-body", ".legal-page"):
        rule = css[css.index(selector + " {"):]
        rule = rule[:rule.index("}")]
        assert "safe-area-inset-top" in rule, selector
        assert "safe-area-inset-bottom" in rule, selector


def test_amount_cards_shrink_instead_of_pushing_the_page_sideways():
    """‎1fr‎ לא מתכווץ מתחת לתוכן. עם אגורות, שלושת הכרטיסים בבית דחפו את
    העמוד הצידה ב-390 וחתכו את החסכונות ב-375 (tests/browser/narrow_screens.py)."""
    css = re.sub(r"/\*.*?\*/", "", _read("frontend/static/css/style.css"), flags=re.S)

    def rule(selector):
        body = css[css.index(selector + " {"):]
        return body[:body.index("}")]

    for grid in (".summary-cards", ".hero-totals", ".kpi-chips"):
        assert "minmax(0, 1fr)" in rule(grid), grid
    assert "cqi" in rule(".summary-card .card-amount")
    assert "cqi" in rule(".kpi-chip .kpi-value")
    # עמוד ההשוואה: טבלה בעמודות קבועות במקום שורה שגלשה (ראו test_the_compare_page_is_one_table)
    assert "table-layout: fixed" in rule(".months-table")


def test_the_onboarding_points_to_a_settings_group_that_exists():
    """מסך הפתיחה אומר "הגדרות ← המשפחה שלי" — והקבוצה נקראה "המשפחה".
    מתן בחר לשנות את שם הקבוצה (30.9), כך שההפניה נכונה."""
    onboarding = _read("frontend/templates/onboarding.html")
    titles = re.findall(r'class="group-title">([^<]+)<', _read("frontend/templates/settings.html"))

    for target in re.findall(r"הגדרות ← ([^.<,\n]+)", onboarding):
        assert target.strip() in titles, target


def test_the_compare_page_compares_and_does_not_sum_everything():
    """מתן (30.9): "זה עמוד השוואה בין החודשים בלבד, מבלי לסכום". הסכום
    הכולל גם לא אמר על איזו תקופה הוא."""
    html = re.sub(r"\{#.*?#\}", "", _read("frontend/templates/months.html"), flags=re.S)

    assert 'סה"כ' not in html and "סה״כ" not in html
    assert "archive | sum(" not in html


def test_the_link_next_to_recent_transactions_says_where_it_goes():
    """האחרונות הן מכל החודשים; הקישור פותח רק את החודש הנוכחי."""
    html = _read("frontend/templates/index.html")
    recent = html[html.index("<h2>עסקאות אחרונות</h2>"):]
    link = recent[recent.index('class="see-all-link"'):]
    link = link[link.index(">") + 1:link.index("</a>")]

    assert link == "לכל החודש"


def test_a_successful_save_releases_the_save_button():
    """אחרי הצלחה הכפתור נשאר "שומר…", וברענון רך העריכה הבאה לא נשלחה
    (מתן, 30.9: "לפעמים זה לא נותן לי ללחוץ על שמירת שינויים").
    בדפדפן: tests/browser/edit_twice.py."""
    js = _strip_comments(_read("frontend/static/js/transactions.js"))
    finish = js[js.index("function finish()"):]
    finish = finish[:finish.index("closeModal();")]
    assert "setSubmitBusy(false)" in finish
    for opener in ("function openAddModal()", "function openEditModal("):
        body = js[js.index(opener):]
        assert "setSubmitBusy(false)" in body[:body.index("formSeq++") + 60], opener


@pytest.mark.parametrize("kind", ["income", "expense", "savings"])
def test_each_summary_leads_to_its_breakdown(kind):
    """מתן (30.9): לחיצה על "הכנסות" בבית או בעמוד החודש → הפירוט שלהן.
    בדפדפן: tests/browser/cards_to_breakdown.py."""
    month = _read("frontend/templates/month.html")
    home = _read("frontend/templates/index.html")

    assert f'id="{kind}-breakdown"' in month
    assert f'href="#{kind}-breakdown"' in month
    assert f"url_for('month_view') }}}}#{kind}-breakdown" in home


def test_what_is_left_is_not_a_link():
    """המאזן החודשי לא שייך לקטגוריה אחת — מתן בחר להשאיר אותו לא לחיץ."""
    month = _read("frontend/templates/month.html")
    label = month.index("מאזן החודש</p>")
    opening = month[month.rindex("month-net", 0, label) - 20:label]
    assert "<a " not in opening and "kpi-link" not in opening


def test_the_card_you_jump_to_stays_visible():
    """‎.anim-rise‎ מתחיל ב-‎opacity: 0‎ ונשאר גלוי רק דרך האנימציה שלו. ההבהוב
    החליף אותה, והכרטיס שאליו קפצו נעלם (מתן: "כאילו מחוק"). בדפדפן:
    tests/browser/cards_to_breakdown.py מדפיס את ה-opacity."""
    css = re.sub(r"/\*.*?\*/", "", _read("frontend/static/css/style.css"), flags=re.S)
    rule = css[css.index(".chart-card.flash {"):]
    rule = rule[:rule.index("}")]
    assert "opacity: 1" in rule


def test_the_card_you_jump_to_stops_below_the_iphone_status_bar():
    """‎scroll-margin-top: 14px‎ עצר את הפירוט מתחת לשעון ולאי הדינמי."""
    css = re.sub(r"/\*.*?\*/", "", _read("frontend/static/css/style.css"), flags=re.S)
    rule = css[css.index("#savings-breakdown {"):]
    rule = rule[:rule.index("}")]
    assert "scroll-margin-top" in rule and "safe-area-inset-top" in rule


def test_the_project_field_is_last_in_the_form():
    """מתן (30.9): רוב העסקאות לא בפרויקט, אז השדה לא יושב אחרי הסכום.
    בדפדפן: tests/browser/project_field_at_bottom.py."""
    base = _read("frontend/templates/base.html")
    form = base[base.index('id="txForm"'):base.index('id="submitBtn"')]
    assert form.index('id="projectGroup"') > form.index('id="txRecurring"')
    assert form.index('id="projectGroup"') > form.index('id="categoryGrid"')


def test_choosing_a_project_takes_you_to_its_categories():
    js = _strip_comments(_read("frontend/static/js/transactions.js"))
    handler = js[js.index("txProject.addEventListener('change'"):]
    handler = handler[:handler.index("});")]
    assert "scrollIntoView" in handler and "refreshCategoryGrid()" in handler


def test_a_project_shows_its_latest_five_and_the_rest_behind_a_button():
    """מתן (30.9): לא רשימה ענקית בעמוד הפרויקט. בדפדפן:
    tests/browser/project_tx_collapsed.py."""
    html = _read("frontend/templates/project_detail.html")
    assert "{% set first_shown = 5 %}" in html
    assert "loop.index > first_shown %} tx-extra" in html
    assert 'id="showAllProjectTx"' in html and 'aria-controls="projectTxList"' in html
    css = _read("frontend/static/css/style.css")
    assert "#projectTxList:not(.show-all) .tx-extra { display: none; }" in css


def test_the_show_all_button_works_without_the_chart_library():
    """הבלוק של הגרפים יוצא מוקדם כשאין Chart.js — הכפתור לא יכול לשבת בתוכו."""
    js = _strip_comments(_read("frontend/static/js/project-detail.js"))
    charts_guard = js.index("if (!window.sfCharts.ready) return;")
    handler = js.index("#showAllProjectTx")
    charts_block_end = js.index("})();", charts_guard)
    assert handler > charts_block_end


@pytest.mark.parametrize("track_income,income,spent,expected", [
    (True, 1000.50, 300.25, "+₪700.25"),
    (True, 100, 350, "-₪250"),
    (True, 100, 100, "₪0"),
    (False, 0, 50, None),
], ids=["surplus", "deficit", "even", "expense-only-project"])
def test_the_project_shows_income_minus_expenses(track_income, income, spent, expected):
    """מתן (30.9): מאזן הפרויקט בנפרד, הכנסות פחות הוצאות. בדפדפן:
    tests/browser/project_net.py."""
    from backend.app import app
    html = _read("frontend/templates/project_detail.html")
    start = html.index("{% if project.track_income and project.track_expense %}")
    end = html.index("</div>\n{% endif %}", start) + len("</div>\n{% endif %}")   # הסוגר של הבלוק, לא של הסימן
    project = {"track_income": track_income, "track_expense": True, "income": income, "spent": spent}
    out = app.jinja_env.from_string(html[start:end]).render(project=project)

    if expected is None:
        assert "project-net" not in out
    else:
        value = out[out.index('class="project-net-value">') + 26:out.index("</p>", out.index("project-net-value"))]
        assert value.strip() == expected, value


def test_the_project_value_sits_above_the_squares_with_its_short_name():
    """מתן (30.9): רק "עלות / שווי הפרויקט", למעלה, ומתחת הוצאות והכנסות שווים."""
    html = _read("frontend/templates/project_detail.html")
    assert "<p class=\"kpi-label\">עלות / שווי הפרויקט</p>" in html
    assert html.index('class="project-net') < html.index('<div class="hero-totals"')


@pytest.mark.parametrize("chips,columns", [(2, 2), (3, 3), (4, 2), (5, 3), (1, 1)])
def test_the_squares_share_the_row_evenly(chips, columns):
    from backend.app import app
    html = _read("frontend/templates/project_detail.html")
    rule = html[html.index("{% set chip_count"):html.index("{% set columns")]
    rule = html[html.index("{% set columns"):html.index("%}", html.index("{% set columns")) + 2]
    out = app.jinja_env.from_string(rule + "{{ [columns, 1] | max }}").render(chip_count=chips)
    assert out.strip() == str(columns)


def test_the_compare_page_is_one_table():
    """מתן (30.9) בחר בטבלה: שורה לחודש, עמודה לסוג. בכרטיס לכל חודש המאזן
    דרס את "חיסכון" ברוחב טלפון. בדפדפן: tests/browser/months_table.py."""
    html = re.sub(r"\{#.*?#\}", "", _read("frontend/templates/months.html"), flags=re.S)
    # טבלה לכל שנה (בתוך הלולאה על השנים), והשנה מעליה ולא בתוכה
    loop = html[html.index("groupby('year')"):]
    assert loop.index('class="year-title"') < loop.index('<table class="months-table">')
    assert "year-row" not in html
    # השנה הנוכחית פתוחה, שנים קודמות רק ככותרת שנפתחת (מתן, 30.9)
    assert '<details class="year-block chart-card" {% if year_group.grouper >= today_year %}open{% endif %}>' in html
    assert '<summary class="year-title">' in html
    assert "showMoreMonths" not in html
    heads = re.findall(r'<th scope="col"[^>]*>([^<]+)</th>', html)
    assert heads == ["חודש", "הכנסות", "הוצאות", "חיסכון", "מאזן"]
    assert "month-stats" not in html and "month-link" not in html


def test_a_receipt_does_not_make_the_row_taller():
    """מתן (30.9). בדפדפן: tests/browser/receipt_row_height.py."""
    home = _read("frontend/templates/index.html")
    row = home[home.index('<div class="tx-amount-row">'):]
    row = row[:row.index("</div>")]
    assert 'class="receipt-badge"' in row, "הסיכה לא באותה שורה עם הסכום"
    css = re.sub(r"/\*.*?\*/", "", _read("frontend/static/css/style.css"), flags=re.S)
    rule = css[css.index(".tx-amount-row .receipt-badge {"):]
    rule = rule[:rule.index("}")]
    assert "margin-block: -4px" in rule


def test_the_compare_chart_reads_right_to_left():
    """מתן (30.9): הגרף בעמוד ההשוואה הפוך — מימין לשמאל."""
    js = _strip_comments(_read("frontend/static/js/months.js"))
    scales = js[js.index("scales: {"):]
    assert re.search(r"x:\s*\{\s*reverse:\s*true", scales)
    assert "position: 'right'" in scales[:scales.index("}\n            }")]


def test_within_each_month_income_is_on_the_right_then_expenses_then_savings():
    """מתן (30.9). ‎Chart.js‎ מסדר את העמודות בכל חודש משמאל לימין, ולכן
    הרשימה בקוד הפוכה: חיסכון, הוצאות, הכנסות."""
    js = _read("frontend/static/js/months.js")
    labels = re.findall(r"label:\s*'([^']+)'", js[js.index("datasets: ["):])[:3]
    assert labels == ["חיסכון", "הוצאות", "הכנסות"]
    assert "maxRotation: 0" in js


def test_the_compare_chart_fills_its_card():
    """מתן (30.9): הגרף והכיתוב גדולים יותר, והגרף רחב — לא גבוה."""
    css = _read("frontend/static/css/style.css")
    # רחב ולא גבוה (מתן, 30.9)
    assert ".line-chart-wrap.compare-chart-wrap { margin-inline: -10px; }" in css
    assert "compare-chart-wrap { height" not in css
    js = _read("frontend/static/js/months.js")
    assert "font: { size: 13 }" in js and "font: { size: 14 }" in js
    assert "SHORT_MONTHS[d.month]" in js, "בגופן הגדול השמות המלאים נדבקים זה לזה"


def test_the_chart_canvas_fills_its_wrap_in_safari_rtl():
    """מתן (30.9): באייפון הגרף תפס רק כ-2/3 מהרוחב. ב-Safari ב-RTL ה-canvas
    (300px כברירת מחדל) מקבל ‎margin-left‎ מחושב, ו-Chart.js מחסיר אותו
    מהרוחב — הגרף נתקע על 300. רוחב מפורש ל-canvas מבטל את זה."""
    css = _read("frontend/static/css/style.css")
    rule = re.search(r"\.line-chart-wrap canvas,\s*\.doughnut-wrap canvas\s*\{([^}]*)\}", css)
    assert rule, "חסר כלל רוחב ל-canvas של הגרפים"
    assert "width: 100% !important" in rule.group(1)


def test_the_savings_legend_says_of_what():
    """מתן (30.9): "חסכתם 67%" לא אומר ממה — כמו ההוצאות, "מההכנסות"."""
    html = _read("frontend/templates/index.html")
    assert "חסכתם {{ saved_pct }}% מההכנסות</span>" in html


def test_all_transactions_can_be_filtered_by_type():
    """מתן (30.9, רעיון 5): הכל / הוצאות / הכנסות / חיסכון מעל החיפוש —
    רק הסוגים שיש החודש, ויחד עם החיפוש (לא במקומו)."""
    tpl = _read("frontend/templates/month.html")
    assert 'class="date-chip tx-type-chip active" data-type=""' in tpl
    assert "selectattr(0, 'in', present)" in tpl
    assert "tx_types | length > 1" in tpl
    js = _strip_comments(_read("frontend/static/js/month.js"))
    assert "(!type || row.dataset.type === type)" in js
    assert "(!q || desc.toLowerCase().indexOf(q) !== -1)" in js
    assert "count.dataset.total" in js


def test_the_category_row_filters_several_categories_together():
    """מתן (30.9, אפשרות א): "כל ההוצאות" או כמה קטגוריות יחד."""
    tpl = _read("frontend/templates/month.html")
    assert 'data-cat-key="{{ tx.get(\'cat_key\', \'\') }}"' in tpl
    assert 'class="date-chip tx-cat-chip active" data-cat=""' in tpl
    js = _strip_comments(_read("frontend/static/js/month.js"))
    assert "(!cats.size || cats.has(row.dataset.catKey))" in js
    assert "pressChip(catChip, !catChip.classList.contains('active'))" in js


def test_the_form_date_chips_ignore_other_chips_on_the_page():
    """כפתורי הסינון לובשים ‎.date-chip‎. כשהטופס תפס את כולם, לחיצה על
    "הוצאות" שינתה את התאריך בטופס, וסימנה את כל הכפתורים כפעילים."""
    js = _strip_comments(_read("frontend/static/js/transactions.js"))
    assert "querySelectorAll('.date-chip')" not in js
    assert js.count("querySelectorAll('.date-quick-chips .date-chip')") == 2


def test_the_plus_on_a_project_page_starts_in_that_project():
    """מתן (30.9, רעיון 8): הפרויקט כבר בחור, והסוג הוא סוג שהוא עוקב אחריו."""
    tpl = _read("frontend/templates/project_detail.html")
    assert '<span id="sfPageProject" data-project-id="{{ project.id }}" hidden></span>' in tpl
    js = _strip_comments(_read("frontend/static/js/transactions.js"))
    assert "document.getElementById('sfPageProject')" in js
    assert "setType(type, undefined, undefined, project ? project.id : undefined)" in js
    assert ": project.track_income ? 'income' : 'savings'" in js
    # החלפת סוג לא מאפסת את הפרויקט
    assert "setType('income', undefined, undefined, txProject.value)" in js


def test_tapping_a_month_in_the_compare_chart_opens_it():
    """מתן (30.9, רעיון 10) — לפי העמודה כולה, לא רק העמודה שנפגעה."""
    js = _strip_comments(_read("frontend/static/js/months.js"))
    assert "getElementsAtEventForMode(evt, 'index', { intersect: false }, true)" in js
    assert "'/month?year=' + d.year + '&month=' + d.month" in js


def test_there_is_one_form_for_a_new_project():
    """מתן (30.9, רעיון 13): ההגדרות מובילות לטופס המלא בעמוד הפרויקטים,
    ולא מחזיקות עותק מקוצר בלי אייקון ובלי תיאור."""
    settings = _read("frontend/templates/settings.html")
    assert "newProjectSettingsForm" not in settings
    assert "href=\"{{ url_for('projects') }}#new\"" in settings
    js = _strip_comments(_read("frontend/static/js/projects.js"))
    assert "window.location.hash === '#new'" in js
    # עריכת פרויקט בהגדרות ממשיכה לעבוד — הקוד שלה ישב אחרי יציאה מוקדמת
    # שתלויה בכפתור היצירה שהוסר
    sjs = _strip_comments(_read("frontend/static/js/settings.js"))
    assert "newProjectSettingsBtn" not in sjs
    assert "closest('.edit-project-settings-btn')" in sjs


def test_pull_to_refresh_only_in_the_installed_app_and_only_from_the_top():
    """מתן (30.9, רעיון 14). ב-Safari רגיל זה קיים מעצמו; כפול היה מרענן פעמיים."""
    js = _strip_comments(_read("frontend/static/js/pwa.js"))
    part = js[js.index("const TRIGGER = 70"):]
    assert "if (!isStandalone || !('ontouchstart' in window)) return;" in js
    assert "return busy || window.scrollY > 0" in part
    assert "if (dy < 0 || Math.abs(dx) > Math.abs(dy))" in part
    assert "'.modal-overlay.open, .transaction-item.open, .confirm-overlay.open, '" in part
    assert "document.querySelector(OPEN_WINDOWS)" in part
    assert "document.querySelector('main[data-soft-reload]') && window.softReload" in part


def test_the_category_card_draws_the_average_and_this_month_lighter():
    """מתן (30.9, סבב 6 פריט 1): "לפי קטגוריה" בעמוד ההשוואה."""
    js = _strip_comments(_read("frontend/static/js/months.js"))
    assert "c.avg == null ? [] : c.values.map(() => c.avg)" in js
    assert "(isNow && i === months.length - 1) ? BAR_NOW : BAR" in js
    tpl = _read("frontend/templates/months.html")
    assert "'cat_trend': cat_trend" in tpl and 'id="categoryChart"' in tpl


def test_the_search_screen_sits_outside_main_and_rows_open_for_editing():
    """מתן (30.9, סבב 6 פריט 2): מחוץ ל-‎main‎ כדי שרענון רך לא יסגור אותו,
    ומתחת לחלון העריכה כדי שנגיעה בתוצאה תפתח אותו מעליו."""
    tpl = _read("frontend/templates/index.html")
    assert tpl.index('id="searchScreen"') > tpl.index("{% block scripts %}")
    assert 'id="searchOpen"' in tpl
    js = _strip_comments(_read("frontend/static/js/search.js"))
    assert "li.className = 'cat-tx-row'" in js and "d.id = tx.id" in js
    assert "window.addEventListener('sf:refreshed'" in js
    css = _read("frontend/static/css/style.css")
    assert "position: fixed; inset: 0; z-index: 95;" in css


def test_a_finished_project_is_not_offered_but_an_old_transaction_keeps_it():
    """מתן (30.9, סבב 6 פריט 3). בלי זה, עריכת סכום של עסקה בפרויקט שהסתיים
    הייתה מוציאה אותה ממנו אל הוצאות הבית — הוא פשוט לא היה ברשימה."""
    js = _strip_comments(_read("frontend/static/js/transactions.js"))
    assert "window.sfFetchList('/api/projects?include_archived=1')" in js
    assert "(p[trackKey] && !p.archived)" in js
    assert "|| (keepOriginal && p.id === selectedProjectId)" in js


def test_a_finished_project_is_reopened_not_returned_to_the_active():
    """מתן (30.9): "החזרה לפעילים" לא מצא חן — "פתיחה מחדש"."""
    for f in ("frontend/templates/project_edit.html", "frontend/templates/project_detail.html",
              "frontend/static/js/core.js"):
        assert "לפעילים" not in _read(f), f
    assert "פתיחה מחדש" in _read("frontend/templates/project_detail.html")
    assert "'הפרויקט נפתח מחדש'" in _read("frontend/static/js/core.js")


def test_categories_can_be_dragged_into_order():
    """מתן (30.9, סבב 6 פריט 5). ההאזנה על document: הזזת השורה ב-DOM
    שחררה את ‎setPointerCapture‎ והגרירה נעצרה אחרי צעד אחד, בלי לשמור."""
    tpl = _read("frontend/templates/settings.html")
    assert 'class="cat-drag-handle" aria-hidden="true"' in tpl
    assert 'class="cat-move-btn cat-move-up"' in tpl        # החצים נשארים
    js = _strip_comments(_read("frontend/static/js/settings.js"))
    part = js[js.index("closest('.cat-drag-handle')"):]
    assert "document.addEventListener('pointermove', move)" in part
    assert "setPointerCapture" not in part
    assert "if (after !== before) persistCategoryOrder(panel);" in part
    css = _read("frontend/static/css/style.css")
    assert "touch-action: none; user-select: none;" in css


def test_a_new_transaction_is_checked_before_it_is_saved():
    """מתן (30.9, סבב 6 פריטים 6–7): רק עסקה חדשה — לא עריכה. תקלה ברשת
    בבדיקה לא עוצרת את השמירה."""
    js = _strip_comments(_read("frontend/static/js/transactions.js"))
    assert "if (!editId && precheckPassed !== precheckKey(payload))" in js
    assert ".catch(function () { return {}; })" in js
    assert "confirmText: 'להוסיף בכל זאת'" in js and "cancelText: 'לתקן'" in js
    # הבדיקה לפני השמירה עצמה, ולא אחריה
    assert js.index("precheckPassed !== precheckKey(payload)") < js.index("submitLabel.textContent = 'שומר…'")


def test_an_edit_can_be_undone_from_the_toast():
    """מתן (30.9, סבב 6 פריט 10): בחלון העריכה ובעורך שבשורה בדף הבית.
    לא אחרי "עדכן להבא" — הביטול היה מחזיר רק חצי מהשינוי."""
    js = _strip_comments(_read("frontend/static/js/transactions.js"))
    assert "Object.assign({}, spec.body, { if_match: spec.if_match })" in js
    assert "!(followUp && (followUp.series || followUp.error))" in js
    assert "rememberUndo(undoSpec(tx, data.transaction, 'העסקה עודכנה'))" in js
    assert "{ label: 'בטל', onClick: function () { runUndo(spec); } }" in js


def test_the_date_chips_include_the_day_before_yesterday():
    """מתן (30.9, סבב 6 פריט 11)."""
    tpl = _read("frontend/templates/base.html")
    chips = tpl[tpl.index('class="date-quick-chips"'):]
    chips = chips[:chips.index("</div>")]
    assert [d for d in ("0", "-1", "-2") if f'data-days="{d}"' in chips] == ["0", "-1", "-2"]
    assert ">שלשום<" in chips


def test_the_month_header_stays_on_top_once_the_balance_scrolls_away():
    """מתן (30.9, סבב 6 פריט 12). רק כשהמאזן יצא למעלה, והסכום הסופי —
    לא מספר הביניים של אנימציית הספירה."""
    js = _strip_comments(_read("frontend/static/js/month.js"))
    assert "bar.hidden = e.isIntersecting || e.boundingClientRect.top > 0;" in js
    assert "window.sfMoney(valueEl.dataset.countup)" in js
    assert "window.addEventListener('sf:refreshed', build);" in js
    css = _read("frontend/static/css/style.css")
    assert "padding: calc(env(safe-area-inset-top, 0px) + 10px) 18px 10px;" in css


def test_a_slow_page_change_shows_a_skeleton_and_a_fast_one_does_not():
    """מתן (30.9, סבב 6 פריט 14): רק אחרי רבע שנייה, רק לעמודים שיש להם צורה,
    ולא נשאר תקוע כשחוזרים אחורה מהמטמון של הדפדפן."""
    js = _strip_comments(_read("frontend/static/js/skeleton.js"))
    assert "const DELAY = 250;" in js
    for page in ("'/'", "'/month'", "'/months'", "'/projects'", "'/settings'"):
        assert page + ":" in js
    assert "window.addEventListener('pageshow', hide);" in js
    assert "if (e.defaultPrevented" in js
    assert "js/skeleton.js" in _read("frontend/templates/base.html")


def test_every_page_is_a_pixel_taller_than_the_screen():
    """מתן (30.9): באפליקציה המותקנת התפריט התחתון "עלה" בעמוד הפרויקטים —
    העמוד היחיד שהיה קצר מהמסך. ‎lvh‎ (המסך הגדול) ולא ‎dvh‎."""
    css = _read("frontend/static/css/style.css")
    body = css[css.index("\nbody {"):]
    body = body[:body.index("}")]
    assert "min-height: calc(100lvh + 1px);" in body
    assert "100dvh" not in body


def test_tapping_a_month_in_the_category_chart_opens_its_expenses():
    """מתן (30.9): חלון עם ההוצאות של הקטגוריה באותו חודש."""
    js = _strip_comments(_read("frontend/static/js/months.js"))
    assert "chart.options.onClick = function (evt)" in js
    assert "const items = (current.items || [])[i] || [];" in js
    assert "'לא בוצעו עסקאות בקטגוריה בחודש זה'" in js
    assert "link.textContent = 'לעמוד החודש';" in js


def test_the_category_chart_title_label_and_month_link():
    """מתן (1.10): כותרת "הוצאות לפי קטגוריה", בלי תווית שחורה צפה על הגרף,
    ו"לעמוד החודש" פותח את העמוד מלמעלה ולא חתוך בפירוט."""
    tpl = _read("frontend/templates/months.html")
    assert '<h2 class="chart-title">הוצאות לפי קטגוריה</h2>' in tpl
    js = _strip_comments(_read("frontend/static/js/months.js"))
    cat = js[js.index("const chart = new Chart(catCanvas"):js.index("plugins: [valuesOnTop]")]
    assert "tooltip: { enabled: false }" in cat
    assert "link.href = '/month?year=' + m.year + '&month=' + m.month;" in js
    assert "#expense-breakdown';" not in js[js.index("function openMonth"):]
    css = _read("frontend/static/css/style.css")
    assert ".cat-trend-stats > div { display: flex; flex-direction: column; align-items: center; text-align: center; }" in css
    assert "const cell = (label, value) => '<div><span>' + label + '</span><b>' + value + '</b></div>';" in js
    assert "cell('החודש הכי יקר' + (c.max_label ? ' <span class=\"nowrap\">- ' + c.max_label + '</span>' : '')," in js


def test_the_month_strip_recenters_after_a_soft_reload():
    """מתן (1.10): הרענון הרך מחליף את ה-hero ברצועה שעומדת בהתחלה — יולי
    ואוגוסט על המסך כשהחודש הוא אוקטובר. בדפדפן: tests/browser/month_strip_center.py."""
    js = _strip_comments(_read("frontend/static/js/month.js"))
    assert "centerStrip();" in js
    assert "window.addEventListener('sf:refreshed', centerStrip);" in js
    body = js[js.index("function centerStrip()"):js.index("centerStrip();")]
    assert "document.getElementById('monthStrip')" in body, "הרצועה נשלפת מחדש בכל קריאה, לא נשמרת מהטעינה"


# ─── סקירה של 1.10 ───────────────────────────────────────────────────────────

def test_closing_the_form_during_the_check_cancels_the_save():
    """הטופס נסגר בזמן "בודק…" — העסקה נשמרה בכל זאת, עם קבלה שהסגירה מחקה."""
    js = _strip_comments(_read("frontend/static/js/transactions.js"))
    part = js[js.index("runPrecheck(payload).then(function (ok) {"):]
    part = part[:part.index("requestSubmit();")]
    assert "if (!overlay.classList.contains('open')) return;" in part


def test_pull_to_refresh_leaves_open_windows_alone():
    """בתוך חיפוש/חלון, גרירה למטה היא גלילה של הרשימה — לא רענון של העמוד."""
    js = _strip_comments(_read("frontend/static/js/pwa.js"))
    for sel in (".search-screen:not([hidden])", ".icon-picker:not([hidden])",
                ".color-sheet:not([hidden])", ".confirm-overlay.open"):
        assert sel in js, sel
    assert "document.querySelector(OPEN_WINDOWS)" in js


def test_the_skeleton_rechecks_before_it_shows():
    js = _strip_comments(_read("frontend/static/js/skeleton.js"))
    part = js[js.index("timer = setTimeout(function () {"):]
    assert part.index("if (e.defaultPrevented) return;") < part.index("overlay = build(shape);")
