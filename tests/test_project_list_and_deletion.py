"""רשימת הפרויקטים הציגה סכום ו-✕, ושניהם היו במקום הלא נכון.

**הסכום** דורש הקשר שאין ברשימה: ₪4,200 מתוך מה? על פני כמה זמן? מול
איזה יעד? בתוך הפרויקט כל זה מוצג ממילא.

**וה-✕** היה הפעולה הבלתי הפיכה ביותר בעמוד, במרחק נגיעה אחת מהשם של
הפרויקט, בלי שום מידע על מה עומד להימחק. היא נשאלה בשתי שאלות רצופות
כי לא היה שום דבר אחר שיספר מה יאבד.

שניהם עברו לתוך הפרויקט. שם המשתמש כבר ראה את הסכומים ואת העסקאות,
ואזור המחיקה אומר במפורש כמה עסקאות עומדות על הפרק.
"""
import re
from pathlib import Path

import pytest

from backend import supabase_config as db
from backend.app import app, limiter
from tests._fake_db import FakeSupabase

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_LIST = (_ROOT / "frontend/templates/projects.html").read_text(encoding="utf-8")
_EDIT = (_ROOT / "frontend/templates/project_edit.html").read_text(encoding="utf-8")
_JS = _ROOT / "frontend/static/js"

_FAM, _ME = "f" * 8, "m" * 8


# ─── הרשימה: שמות בלבד ───────────────────────────────────────────────────────

def test_the_list_shows_no_amounts():
    """סכום בלי הקשר הוא מספר שאי אפשר לעשות איתו כלום."""
    rows = _LIST[_LIST.index('id="projectsList"'):]
    rows = rows[:rows.index("</ul>")]

    assert "project-amount" not in rows


def test_the_list_has_no_delete_button():
    """✕ ליד השם, בלי לדעת מה יימחק."""
    assert "delete-project-btn" not in _LIST


def test_nothing_still_listens_for_that_button():
    """מאזין יתום הוא באג שממתין למי שיחזיר את ה-HTML."""
    owners = [f.name for f in _JS.glob("*.js")
              if "closest('.delete-project-btn')" in f.read_text(encoding="utf-8")]

    assert owners == [], f"עדיין יש מאזין ב: {owners}"


def test_the_row_still_says_it_can_be_opened():
    """שורה בלי סכום היא שורה בלי משקל מימין — בלי סימן, היא נראית
    כמו טקסט ולא כמו כניסה."""
    assert "project-chevron" in _LIST
    assert "project_detail" in _LIST


def test_the_name_and_description_survived():
    """בקרת-נגד: הורדנו סכום ומחיקה, לא את התוכן."""
    assert "project-name" in _LIST
    assert "p.description" in _LIST


# ─── בתוך הפרויקט: הסכום והמחיקה ─────────────────────────────────────────────

def test_the_project_page_still_shows_the_totals():
    """זה המקום שאליו הסכום עבר."""
    detail = (_ROOT / "frontend/templates/project_detail.html").read_text(encoding="utf-8")

    assert "hero-totals" in detail
    assert "project.spent" in detail


def test_deletion_lives_in_the_projects_own_management():
    assert "project-danger" in _EDIT
    assert 'id="confirmDeleteProjectBtn"' in _EDIT


def test_it_says_how_many_transactions_will_be_affected():
    """✕ ברשימה לא נשא שום מספר."""
    block = _EDIT[_EDIT.index("project-danger"):]

    assert "tx_count" in block
    assert "אין לפרויקט עסקאות" in block, "פרויקט ריק מקבל ניסוח משלו"


def test_the_default_keeps_the_money():
    """מחיקת פרויקט אינה מחיקת ההוצאות שנרשמו בו — הן קרו."""
    block = _EDIT[_EDIT.index("project-danger"):]
    active = re.search(r'class="toggle-btn active" data-tx-mode="(\w+)"', block)

    assert active and active.group(1) == "keep"

    js = (_JS / "project-edit.js").read_text(encoding="utf-8")
    assert "let txMode = 'keep';" in js, "ה-JS מתחיל ממצב אחר מהסימון החזותי"


def test_choosing_to_delete_changes_what_the_hint_says():
    """בלי זה הבחירה נראית כמו העדפה ולא כמו החלטה על כסף."""
    js = (_JS / "project-edit.js").read_text(encoding="utf-8")

    assert "projectTxModeHint" in js
    assert "לא יופיעו בשום דוח" in js


# ─── ושהמסלול באמת עושה את שתי הפעולות ───────────────────────────────────────

@pytest.fixture
def project(monkeypatch):
    limiter.reset()
    app.config["TESTING"] = True
    fake = FakeSupabase(
        projects=[{"id": "p1", "family_id": _FAM, "name": "שיפוץ", "owner_id": None,
                   "archived": False, "track_expense": True,
                   "track_income": False, "track_savings": False}],
        transactions=[{"id": f"t{i}", "family_id": _FAM, "project_id": "p1",
                       "amount": 100.0, "type": "expense", "date": "2026-09-01"}
                      for i in range(3)],
    )
    monkeypatch.setattr(db, "get_client", lambda: fake)
    monkeypatch.setattr(db, "get_project_for_transaction",
                        lambda pid, fid: {"id": pid, "owner_id": None,
                                          "track_expense": True, "track_income": False,
                                          "track_savings": False})
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = _ME
            sess["family_id"] = _FAM
        yield c, fake


def test_keeping_the_transactions_leaves_every_one_of_them(project):
    c, fake = project

    res = c.delete("/api/projects/p1", json={"delete_transactions": False})

    assert res.status_code == 200
    assert res.get_json()["deleted"] == 0
    assert len(fake.rows("transactions")) == 3, "עסקאות נמחקו למרות הבחירה"
    assert fake.rows("projects") == []


def test_deleting_them_reports_the_real_number(project):
    """המספר מגיע מהשרת ולא מהדפדפן — אחרת הוא הבטחה שלא נבדקה."""
    c, fake = project

    res = c.delete("/api/projects/p1", json={"delete_transactions": True})

    assert res.get_json()["deleted"] == 3
    assert fake.rows("transactions") == []


# ─── ניהול הפרויקט הוא תפריט אחד ────────────────────────────────────────────
#
# העמוד היה ארבעה ‎chart-card‎ נפרדים, כל אחד עם ‎margin-bottom: 16px‎,
# והרביעי (המחיקה) בסגנון אחר לגמרי — כך שמסך אחד של הגדרות נראה כמו
# ארבעה מסכים שהודבקו זה לזה.

def test_the_management_page_is_one_container():
    """כרטיס אחד, לא ארבעה."""
    assert 'class="project-settings"' in _EDIT
    assert 'class="chart-card"' not in _EDIT, \
        "עדיין יש כרטיס נפרד — הרווח ביניהם חוזר"


def test_every_section_became_a_block_inside_it():
    """כל חלק נשאר חלק — רק בלי מסגרת משלו."""
    blocks = _EDIT.count("project-settings-block")
    assert blocks == 4, f"נמצאו {blocks} בלוקים במקום 4"


def test_the_sections_are_separated_by_a_line_and_not_by_a_gap():
    """"תפריט אחד מתמשך עם הפרדות ביניהם" — הקו הוא ההפרדה."""
    body = _EDIT[_EDIT.index('class="project-settings"'):]
    dividers = body.count('class="group-divider"')

    assert dividers == 3, f"{dividers} קווי הפרדה בין 4 חלקים"


def test_the_delete_section_is_part_of_the_same_menu():
    """הוא היה ‎settings-group‎ בזמן שהשאר היו ‎chart-card‎ — אותו מסך,
    שני סגנונות."""
    block = _EDIT[_EDIT.index("project-danger"):]

    assert "settings-group" not in block
    assert "project-settings-block project-danger" in _EDIT


def test_the_container_carries_the_card_styling_now():
    """אם המיכל לא נושא רקע וגבול, ארבעת החלקים פשוט מרחפים על הרקע."""
    css = (_ROOT / "frontend/static/css/style.css").read_text(encoding="utf-8")
    rule = css[css.index(".project-settings {"):]
    rule = rule[:rule.index("}")]

    for prop in ("background", "border", "border-radius"):
        assert prop in rule, f"{prop} חסר — החלקים לא ייראו ככרטיס אחד"


def test_the_dividers_reach_the_edges():
    """קו עם שוליים נראה כמו קו בתוך פסקה, לא כמו גבול בין שני חלקים."""
    css = (_ROOT / "frontend/static/css/style.css").read_text(encoding="utf-8")

    assert ".project-settings > .group-divider { margin: 0; }" in css


# ─── מסך ההגדרות היה צפוף, ושדה אחד בו לא הסביר את עצמו ─────────────────────
#
# שלושה דברים שמתן הצביע עליהם בצילום מסך:
#
# 1. ה-+ הצף ("הוסף עסקה חדשה") ישב בפינה השמאלית התחתונה — בדיוק על
#    "מחק פרויקט". הפעולה הבלתי הפיכה היחידה בעמוד הייתה חצי מוסתרת
#    מאחורי כפתור שאין לו שום משמעות במסך הגדרות.
# 2. שורת הוספת הקטגוריה נגעה בשורה האחרונה ברשימה, כי
#    ‎.category-row:last-child‎ מאפסת את הריפוד התחתון.
# 3. "יעד תקציב" — שדה סכום בלי מילת הסבר אחת.

_DETAIL = (_ROOT / "frontend/templates/project_detail.html").read_text(encoding="utf-8")
_BASE = (_ROOT / "frontend/templates/base.html").read_text(encoding="utf-8")
_CSS = (_ROOT / "frontend/static/css/style.css").read_text(encoding="utf-8")


def _visible(html):
    """בלי הערות. הערה בעברית שמסבירה תיקון מכילה כמעט תמיד את המילים
    של הבאג — וכך בדיקה "עוברת" על טקסט שאף משתמש לא רואה. זה כבר קרה
    כאן, ובפעם הזאת זה גם הפיל את הבדיקה הזאת בעצמה."""
    return re.sub(r"\{#.*?#\}|<!--.*?-->", "", html, flags=re.S)


def test_the_budget_field_is_called_the_same_thing_in_both_places():
    """שם אחד לשדה. סדר מילים הפוך בין שני עמודים קורא כמו שני דברים."""
    for name, html in (("עריכה", _EDIT), ("פרויקט", _DETAIL)):
        shown = _visible(html)
        assert "תקציב יעד" in shown, f"השם החדש לא מופיע ב{name}"
        assert "יעד תקציב" not in shown, f"השם הישן עדיין מוצג ב{name}"


def test_the_budget_field_explains_what_it_does():
    """שדה סכום בלי הסבר משאיר את המשתמש לנחש אם זה תקרה, תחזית או
    כסף שכבר הופרש."""
    hint = _EDIT[_EDIT.index('id="budgetTargetHint"'):]
    hint = hint[:hint.index("</p>")]
    # בלי התגית ובלי הזחה — אחרת רווחים נספרים כהסבר, ו"סכום." בשורה
    # מוזחת "עובר" את בדיקת האורך.
    words = " ".join(hint[hint.index(">") + 1:].split()).split(" ")

    assert len(words) >= 12, f"ההסבר הוא {len(words)} מילים — זה לא הסבר"
    assert 'aria-describedby="budgetTargetHint"' in _EDIT, \
        "ההסבר קיים אבל לא מקושר לשדה, אז קורא מסך לא ישמע אותו"


def test_the_floating_plus_is_gone_from_the_settings_screen():
    """הוא כיסה את כפתור המחיקה."""
    assert "{% block body_class %}no-fab{% endblock %}" in _EDIT
    assert "{% block body_class %}{% endblock %}" in _BASE, \
        "ה-body אינו נושא את הבלוק, אז ה-class לעולם לא מגיע"
    assert "body.no-fab .fab" in _CSS


def test_the_plus_button_itself_still_exists():
    """‎transactions.js‎ עושה ‎fabBtn.addEventListener‎ בלי שום שמירה.
    מחיקת האלמנט מהתבנית תזרוק ותהרוג את כל שאר הקובץ — כולל את
    חלון העסקה. מסתירים, לא מוחקים."""
    assert 'id="fabBtn"' in _BASE

    js = (_JS / "transactions.js").read_text(encoding="utf-8")
    assert "fabBtn.addEventListener" in js, \
        "אם זה כבר מגודר — אפשר למחוק את האלמנט, והבדיקה הזאת מיותרת"


def test_adding_a_category_is_visibly_a_separate_thing():
    """בלי הפרדה, "הוסף" נראה כמו כפתור של הקטגוריה האחרונה ברשימה."""
    rule = _CSS[_CSS.index("#projectCategoriesArea .add-cat-form"):]
    rule = rule[:rule.index("}")]

    import re
    gap = re.search(r"margin-top\s*:\s*(\d+)", rule)
    assert gap and int(gap.group(1)) >= 12, "אין רווח אמיתי בין הרשימה לטופס"
    assert "border-top" in rule, "רק רווח — אין קו שמפריד בין הרשימה לטופס"
