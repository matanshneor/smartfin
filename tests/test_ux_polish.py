"""ארבעה דברים שעבדו נכון והרגישו לא נכון.

אף אחד מהם לא היה באג: האפליקציה חישבה נכון, שמרה נכון והציגה נכון.
הם פשוט הקשו על אדם לעשות את מה שהוא בא לעשות.

1. **שדה שלא רלוונטי במקום השני.** "שייך לפרויקט" הוצג תמיד — גם
   למשפחה בלי אף פרויקט, עם אפשרות אחת: "ללא". בפעולה שעושים עשר
   פעמים ביום, שני שדות מיותרים הם המון.
2. **התכונה המרכזית הייתה בלתי נגישה מהמקום שמוביל אליה.** אדם רואה
   ₪1,240 על מכולת וחושב "כדאי שאשים גבול" — ובעמוד החודש לא הייתה
   אף הפניה להגדרות.
3. **שתי לשונות פנייה, לפעמים באותו מסך.** ה-Hero אומר "לחצו... שלכם"
   והרשימה מתחתיו "לחץ".
4. **המספר הראשון של כל משתמש חדש היה מינוס אדום.** כמעט כולם מזינים
   הוצאה לפני משכורת. חשבונאית זה נכון; בפועל האפליקציה פותחת בהודעה
   שמשהו לא בסדר.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent


def _read(rel):
    return (_ROOT / rel).read_text(encoding="utf-8")


def _strip_comments(js):
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"^\s*//.*$", "", js, flags=re.M)


def _strip_jinja(html):
    return re.sub(r"\{#.*?#\}", "", html, flags=re.S)


# ─── 1. שדה הפרויקט מוסתר כשאין לאן לשייך ────────────────────────────────────

def test_the_project_field_hides_itself_when_there_are_no_projects():
    """הלב. שדה עם אפשרות אחת ("ללא") במקום השני של הטופס הנפוץ ביותר."""
    js = _strip_comments(_read("frontend/static/js/transactions.js"))
    fn = js[js.index("function buildProjectSelect"):]
    fn = fn[:fn.index("\n    }")]

    assert re.search(r"projectGroup\.style\.display\s*=\s*projects\.length", fn), \
        "השדה מוצג גם כשאין פרויקטים"


def test_it_is_not_forced_visible_somewhere_else():
    """‎setType‎ קבע ‎display = ''‎ ללא תנאי, וזה היה דורס כל הסתרה."""
    js = _strip_comments(_read("frontend/static/js/transactions.js"))

    assert "projectGroup.style.display = '';" not in js


def test_the_owner_field_still_hides_the_same_way():
    """בקרת-נגד: הדפוס שממנו העתקתי עדיין קיים."""
    js = _strip_comments(_read("frontend/static/js/transactions.js"))

    assert "ownerGroup.style.display = hasOwner ? '' : 'none';" in js


# ─── 2. אפשר לקבוע תקציב מהמקום שבו מבינים שצריך ─────────────────────────────

def test_the_month_page_offers_to_set_a_budget():
    """עד עכשיו לא הייתה מעמוד החודש **שום** הפניה להגדרות."""
    html = _read("frontend/templates/month.html")

    assert "cat-budget-cta" in html
    assert "url_for('settings') }}#budget-" in html


def test_the_offer_only_appears_where_it_makes_sense():
    """קטגוריה שכבר יש לה תקציב לא צריכה את ההצעה, וקטגוריה בלי הוצאה
    לא מזמינה אותה."""
    html = _read("frontend/templates/month.html")
    block = html[html.index("{% if item.budget %}"):]
    block = block[:block.index("cat-budget-cta") + 200]

    assert "{% elif item.category_id and item.total > 0 %}" in block


def test_settings_lands_on_the_right_category():
    """קישור שנוחת בראש עמוד ההגדרות הוא קישור שלא עוזר."""
    js = _strip_comments(_read("frontend/static/js/settings.js"))
    block = js[js.index("#budget-"):]

    assert ".category-row[data-id=" in block, "לא מאתר את הקטגוריה"
    assert "scrollIntoView" in block, "לא גולל אליה"
    assert "settings-group-header" in block, "לא פותח את הקבוצה הסגורה"
    assert "data-cat-tab" in block, "לא עובר ללשונית של הסוג הנכון"


def test_landing_there_turns_the_budget_on():
    """מי שלחץ "קביעת תקציב" התכוון לקבוע תקציב — לא לנחות על שורה
    שנראית בדיוק כמו קודם ולחפש מה לעשות."""
    js = _strip_comments(_read("frontend/static/js/settings.js"))
    block = js[js.index("#budget-"):]

    assert ".budget-enabled" in block
    assert "toggle.checked = true" in block


def test_the_selectors_it_uses_exist_in_the_template():
    """הקישור שובר בשקט אם שם מחלקה ישתנה בצד השני."""
    html = _read("frontend/templates/settings.html")

    for needed in ("category-row", "budget-enabled", "budget-amount",
                   "cat-tab-panel", "settings-group-header"):
        assert needed in html, f"{needed} לא קיים בתבנית"


# ─── 3. לשון אחת ─────────────────────────────────────────────────────────────

# פנייה בלשון יחיד-זכר בטקסט רץ.
#
# **תוויות כפתורים מוחרגות בכוונה.** "שמור" ו"מחק" על כפתור הם ציווי
# קצר ומקובל, והאפליקציה ממילא מערבת אותם עם שמות פעולה ("ביטול",
# "הצטרפות", "פתיחת חשבון") — זו שאלת סגנון שקדמה לתיקון הזה ולא
# חלק ממנו. מה שכן נשבר הוא **הסבר** שפונה למשתמש בשתי לשונות שונות
# באותו מסך.
_SINGULAR = ["לחץ", "הזן", "בחר", "סמן", "הוסף", "נסה"]

# גבולות מילה עבריים: בלעדיהם "הכ**נסה**" ו"ל**סמן**" נספרים כפנייה
# בלשון יחיד, והבדיקה מדווחת על חמישה קבצים תקינים.
_SINGULAR_RE = re.compile(
    r"(?<![\w\u0590-\u05FF])(" + "|".join(_SINGULAR) + r")(?![\w\u0590-\u05FF])")


def _prose(html):
    """הטקסט הרץ בלבד — בלי תוויות של כפתורים וקישורים."""
    html = _strip_jinja(html)
    html = re.sub(r"<(button|a)\b[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    return re.sub(r"<[^>]+>", " ", html)


@pytest.mark.parametrize("template", sorted(p.name for p in (_ROOT / "frontend/templates").glob("*.html")))
def test_no_template_addresses_the_user_in_the_singular(template):
    """האפליקציה היא למשפחה, והיא מדברת ברבים בכל שאר המקומות. שתי
    לשונות באותו מסך קוראות כמו שני כותבים."""
    found = sorted({m.group(1) for m in
                    _SINGULAR_RE.finditer(_prose(_read(f"frontend/templates/{template}")))})

    assert not found, f"{template} פונה בלשון יחיד: {found}"


def test_the_dashboard_says_the_same_thing_twice_the_same_way():
    """הבולט מכולם: ה-Hero והרשימה מתחתיו, אותו מסך, אותה פעולה."""
    html = _strip_jinja(_read("frontend/templates/index.html"))

    assert html.count("לחצו על +") == 2, "שתי ההנחיות לא מנוסחות אותו דבר"


# ─── 4. חודש בלי הכנסות אינו גירעון ──────────────────────────────────────────

def test_a_month_with_no_income_is_not_shown_as_a_deficit():
    """הלב. כמעט כל משתמש חדש מזין הוצאה לפני משכורת, ואז המסך הראשון
    שלו היה ‎-₪120‎ באדום."""
    html = _read("frontend/templates/index.html")
    hero = html[html.index('class="hero-balance"'):]
    hero = hero[:hero.index("</p>", hero.index("hero-amount"))]

    # **כל** בדיקת הסימן מגודרת, לא רק הראשונה: המחלקה ‎deficit‎,
    # ‎data-prefix‎ וסימן המינוס עצמו הם שלושה מקומות נפרדים, ושכחה של
    # אחד מהם משאירה מינוס אדום על מסך שאין בו גירעון.
    guarded = hero.count("not no_income_yet and summary.remaining < 0")
    total = hero.count("summary.remaining < 0")

    assert total >= 3, f"נמצאו רק {total} בדיקות סימן — המבנה השתנה"
    assert guarded == total, (
        f"{total - guarded} מתוך {total} בדיקות הסימן אינן מותנות בכך "
        f"שיש בכלל הכנסות"
    )


def test_it_says_what_the_number_means_instead():
    """"נשאר בעו״ש" על מספר שאין ממנו מה להחסיר הוא משפט שלא נכון."""
    html = _read("frontend/templates/index.html")

    assert "יצא החודש" in html
    assert "עדיין לא הוזנו הכנסות החודש" in html


def test_the_normal_case_is_untouched():
    """בקרת-נגד: מי שיש לו הכנסות רואה בדיוק מה שראה קודם."""
    html = _read("frontend/templates/index.html")

    assert "נשאר בעו״ש החודש" in html
    assert "מתוך ₪{{ \"{:,.0f}\".format(summary.income) }} הכנסות החודש" in html


# ─── 5. הפס בדשבורד ערבב חיסכון עם הוצאות ───────────────────────────────────
#
# ‎used_pct = (expense + savings) / income‎, והתווית הייתה "נוצלו X%".
# חודש שבו הוצאת 20% מההכנסות וחסכת 69% הוצג כפס זהב **כמעט מלא** עם
# "נוצלו 89%" — כלומר חודש מצוין שנראה כמו אזהרה. כסף שנחסך לא נוצל;
# הוא עבר מקום.
#
# וגרוע מזה: ‎{% if used_pct > 90 %}danger{% endif %}‎ — עוד קצת חיסכון
# והפס היה נצבע באדום. אזהרה על התנהגות טובה.

def test_the_bar_does_not_add_savings_to_spending():
    """הלב. שני הדברים ההפוכים האלה לא יכולים לחלוק מספר אחד."""
    html = _read("frontend/templates/index.html")

    assert "used_pct" not in html, "המספר המאוחד עדיין קיים"
    assert "spent_pct" in html and "saved_pct" in html


def test_spending_is_measured_against_income_alone():
    html = _read("frontend/templates/index.html")
    line = next(l for l in html.split("\n") if "set spent_pct" in l)

    assert "summary.expense / summary.income" in line
    assert "savings" not in line


def test_the_red_warning_follows_spending_and_not_the_total():
    """זה מה שבאמת אמור להדאיג. קודם חיסכון גדול הספיק כדי לצבוע
    את הפס באדום."""
    html = _read("frontend/templates/index.html")
    spent_fill = next(l for l in html.split("\n") if "balance-bar-fill spent" in l)
    saved_fill = next(l for l in html.split("\n") if "balance-bar-fill saved" in l)

    assert "spent_pct > 90" in spent_fill and "danger" in spent_fill
    assert "danger" not in saved_fill
    assert "saved_pct" not in spent_fill, "החיסכון חזר לתוך תנאי האדום"


def test_both_parts_are_drawn_separately():
    """פס אחד בצבע אחד לא יכול להראות חלוקה."""
    html = _read("frontend/templates/index.html")
    bar = html[html.index("balance-bar-split"):]
    bar = bar[:bar.index("balance-bar-legend")]

    assert 'balance-bar-fill spent' in bar
    assert 'balance-bar-fill saved' in bar


def test_the_two_parts_cannot_overflow_the_track():
    """אם הוצאות וחיסכון יחד עוברים 100% (אפשרי — מוציאים מחסכונות),
    החלק השני חייב להצטמצם ולא לדחוף את הפס החוצה."""
    html = _read("frontend/templates/index.html")
    saved = next(l for l in html.split("\n") if 'balance-bar-fill saved' in html and "saved_pct" in l and "width" in l)

    assert "100 - [spent_pct, 100] | min" in saved


def test_the_legend_says_which_colour_is_which():
    """שני צבעים בלי מפתח הם ניחוש."""
    html = _read("frontend/templates/index.html")
    legend = html[html.index("balance-bar-legend"):]
    legend = legend[:legend.index("</div>")]

    assert 'bar-key spent' in legend and 'bar-key saved' in legend
    assert "הוצאות" in legend and "חיסכון" in legend
    assert "נוצלו" not in legend


def test_the_screen_reader_hears_the_spending_number():
    """"התקדמות 89%" על חודש שהוצאת בו 20% הוא אותו שקר, בקול."""
    html = _read("frontend/templates/index.html")
    bar = html[html.index("balance-bar-split") - 200:]
    bar = bar[:bar.index("</div>")]

    assert 'aria-valuenow="{{ spent_pct }}"' in bar
