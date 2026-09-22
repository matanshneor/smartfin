"""שלושה סעיפים בעמוד החודש שלא עשו את מה שהשם שלהם הבטיח.

**"קבוע כל חודש"** — שם שתיאר תדירות אחת מתוך חמש. תבנית שבועית או
דו-שבועית הופיעה תחת כותרת שאומרת שהיא חודשית. ולידו כפתור "ניהול"
שהיה קישור להגדרות: מי שעמד כאן וראה ששכר הדירה שגוי נשלח לעמוד אחר,
לגלול, ולמצוא שם את אותה שורה בדיוק — במקום לגעת בזו שמולו.

**"לאן הלך הכסף החודש"** — הכרטיס מראה שתי פרוסות, הוצאות מול חיסכון.
השם הבטיח פירוט של יעדים.

**"פרויקטים החודש"** — רשימה שטוחה של כל עסקאות הפרויקטים יחד. בחודש עם
שיפוץ וטיול אי אפשר היה להפריד ביניהם, וזו בדיוק השאלה שנשאלת.
"""
from pathlib import Path

import pytest

from backend.supabase_config import project_breakdown_from_rows

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_HTML = (_ROOT / "frontend/templates/month.html").read_text(encoding="utf-8")
_JS = _ROOT / "frontend/static/js"


def _tx(project_id, name, kind, amount, icon="🎯"):
    return {"project_id": project_id, "project_name": name, "project_icon": icon,
            "type": kind, "amount": amount, "id": f"{project_id}-{kind}-{amount}"}


# ═══ הקיבוץ לפי פרויקט ═══════════════════════════════════════════════════════

def test_each_project_is_its_own_row():
    """הלב: שיפוץ וטיול הם שתי שאלות נפרדות."""
    rows = project_breakdown_from_rows([
        _tx("a", "שיפוץ", "expense", 800),
        _tx("a", "שיפוץ", "expense", 3400),
        _tx("b", "טיול", "expense", 1100),
    ])

    assert [r["name"] for r in rows] == ["שיפוץ", "טיול"]
    assert rows[0]["expense"] == 4200
    assert rows[1]["expense"] == 1100


def test_two_projects_with_the_same_name_stay_apart():
    """קיבוץ לפי שם היה מאחד להם את הכסף — אותו באג בדיוק שהיה בפילוח
    הקטגוריות, ושם הוא הסתיר תקציב שלם."""
    rows = project_breakdown_from_rows([
        _tx("a", "טיול", "expense", 1000),
        _tx("b", "טיול", "expense", 2000),
    ])

    assert len(rows) == 2, "שני פרויקטים שונים אוחדו לפי שמם"
    assert {r["expense"] for r in rows} == {1000.0, 2000.0}


def test_income_is_not_netted_against_expense():
    """פרויקט עם החזר כספי היה נראה "זול יותר", ופרויקט דו-כיווני
    מאוזן היה מוצג כ-₪0 — מספר שמסתיר את שני הצדדים."""
    rows = project_breakdown_from_rows([
        _tx("a", "טיול", "expense", 1100),
        _tx("a", "טיול", "income", 300),
    ])

    assert rows[0]["expense"] == 1100
    assert rows[0]["income"] == 300


def test_a_transaction_without_a_project_is_left_out():
    """עסקאות רגילות כבר נספרות במאזן החודשי. ספירה כפולה כאן היא
    בדיוק מה שהסעיף קיים כדי למנוע."""
    rows = project_breakdown_from_rows([
        _tx("a", "שיפוץ", "expense", 800),
        {"project_id": None, "type": "expense", "amount": 50},
    ])

    assert len(rows) == 1
    assert rows[0]["expense"] == 800


def test_projects_are_ordered_by_what_actually_went_out():
    rows = project_breakdown_from_rows([
        _tx("small", "קטן", "expense", 100),
        _tx("big", "גדול", "expense", 5000),
        _tx("mid", "בינוני", "savings", 900),
    ])

    assert [r["name"] for r in rows] == ["גדול", "בינוני", "קטן"]


def test_every_row_carries_its_own_transactions():
    """בלי זה אין מה לפתוח."""
    rows = project_breakdown_from_rows([
        _tx("a", "שיפוץ", "expense", 800),
        _tx("a", "שיפוץ", "expense", 3400),
        _tx("b", "טיול", "expense", 1100),
    ])

    assert len(rows[0]["transactions"]) == 2
    assert len(rows[1]["transactions"]) == 1


def test_a_project_with_no_name_still_gets_a_row():
    """שם חסר הוא נתון חסר, לא סיבה להעלים ₪3,000 מהמסך."""
    rows = project_breakdown_from_rows([
        {"project_id": "x", "type": "expense", "amount": 3000},
    ])

    assert len(rows) == 1 and rows[0]["expense"] == 3000


def test_nothing_in_means_nothing_out():
    assert project_breakdown_from_rows([]) == []


# ═══ מה התבנית מציגה ═════════════════════════════════════════════════════════

def test_the_recurring_section_is_named_for_what_it_holds():
    """"קבוע כל חודש" תיאר תדירות אחת מתוך חמש."""
    assert "עסקאות קבועות" in _HTML
    assert "קבוע כל חודש" not in _HTML


def test_managing_recurring_no_longer_sends_you_to_settings():
    """הלב של הבקשה: הכפתור פותח עריכה כאן, לא עמוד אחר."""
    block = _HTML[_HTML.index("עסקאות קבועות"):][:700]

    assert 'id="fixedManageBtn"' in block
    assert "settings" not in block, "הכפתור עדיין מפנה להגדרות"


def test_the_recurring_rows_carry_what_the_editor_needs():
    """המודאל הגלובלי בונה את העסקה מה-‎data-*‎. חסר אחד — והעריכה
    נפתחת על ערכים שגויים, שנשמרים."""
    block = _HTML[_HTML.index('class="fixed-list"'):][:2500]

    for field in ("data-id", "data-amount", "data-type", "data-category-id",
                  "data-date", "data-is-recurring", "data-recurring-frequency",
                  "data-recurring-end-date", "data-recurring-parent-id"):
        assert field in block, f"{field} חסר בשורת העסקה הקבועה"


def test_the_overview_card_says_what_it_draws():
    """הגרף הוא שתי פרוסות — הוצאות מול חיסכון."""
    assert "הוצאות מול חיסכון" in _HTML
    assert "לאן הלך הכסף החודש" not in _HTML


def _section(title):
    """הסעיף מהכותרת שלו עד הסעיף הבא. אורך קבוע נקטע באמצע — וקטיעה
    כזאת גורמת לבדיקה לדווח על היעדר של מה שפשוט לא הגיע אליו."""
    start = _HTML.index(title)
    nxt = _HTML.find("<!-- Chart", start)
    return _HTML[start:nxt if nxt != -1 else len(_HTML)]


def test_the_projects_section_is_one_row_per_project():
    block = _section("פרויקטים החודש")

    assert "for proj in project_month.projects" in block, "עדיין רשימה שטוחה"
    assert 'aria-expanded="false"' in block, "השורה לא נפתחת"
    assert "for tx in proj.transactions" in block, "אין מה להיפתח אל תוכו"


def test_the_expanded_project_links_to_its_own_page():
    assert "project_detail" in _section("פרויקטים החודש")


# ═══ אין עותק שני של קוד המחיקה ══════════════════════════════════════════════

def test_the_delete_handler_lives_in_exactly_one_file():
    """אותה רשימה מוצגת עכשיו בשני עמודים. שני עותקים של המטפל היו
    הופכים כל תיקון לשניים — בדיוק מה שקרה ל-‎Chart.defaults‎, שם זה
    היה באג משולש."""
    # ‎closest('.delete-recurring-btn')‎ הוא המטפל; ‎querySelector‎ עליו
    # ב-month.js הוא רק קביעת מיקוד במצב ניהול, ולא עותק שני.
    owners = [f.name for f in _JS.glob("*.js")
              if "closest('.delete-recurring-btn')" in f.read_text(encoding="utf-8")]

    assert owners == ["transactions.js"], f"המטפל נמצא ב: {owners}"


def test_the_x_on_the_month_page_asks_about_the_series():
    """בקשה של מתן, וגם תיקון: ✕ נראה כמו מחיקה ועשה משהו אחר — עצר את
    הסדרה והשאיר את ההיסטוריה. עכשיו הוא מוחק, ושואל את אותה שאלה
    שנשאלת בכל מקום אחר: "רק את זו" או "את זו וכל הבאות"."""
    js = (_JS / "transactions.js").read_text(encoding="utf-8")
    block = js[js.index("const btn = e.target.closest('.delete-recurring-btn');"):]
    month = block[block.index("#fixedList"):block.index("בהגדרות: עצירת הסדרה")]

    assert "deleteWithUndo" in month, "✕ בעמוד החודש לא עובר במסלול המחיקה"
    assert "/api/recurring/" not in month, "✕ בעמוד החודש עדיין עוצר במקום למחוק"


def test_the_x_in_settings_still_stops_the_series_without_deleting():
    """בקרת-נגד. "עצירה בלי למחוק" היא פעולה אמיתית שצריך שתהיה איפשהו,
    וההגדרות הן המקום שבו מנהלים את הסדרה ולא חודש מסוים."""
    js = (_JS / "transactions.js").read_text(encoding="utf-8")
    block = js[js.index("בהגדרות: עצירת הסדרה"):]

    assert "/api/recurring/" in block
    assert "deleteWithUndo" not in block


def test_removing_a_row_on_the_month_page_refreshes_the_totals():
    """הסכומים שמעל הרשימה נגזרים מהשורות, אז הסרת שורה בלבד משאירה
    אותם על הערך הישן. ‎deleteWithUndo‎ מרענן בעצמו אחרי חלון ה"בטל"."""
    js = (_JS / "transactions.js").read_text(encoding="utf-8")
    block = js[js.index("function deleteWithUndo"):]
    block = block[:block.index("\n    function ")]

    assert "refreshAfterDelete" in block, "המספרים נשארים תקועים אחרי מחיקה"
