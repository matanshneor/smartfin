"""שני כללים שאף בדיקה לא אכפה, ושניהם נשברו באותו יום.

**מטפל בשורה.** ל-‎onclick‎ בתבנית אין שום סימן שהוא לא עובד: הוא נראה
נכון, הוא עובר כל בדיקת טקסט, והדפדפן חוסם אותו בשקט בגלל ה-CSP
(‎script-src 'self'‎ בלי ‎unsafe-inline‎). הוא נחת על כפתור הרענון במסך
ההמתנה — המסך היחיד באפליקציה שאין ממנו יציאה. הכפתור פשוט לא הגיב.

**רענון רך בלי שומר.** ‎softReload‎ מחליף את ‎main‎ כולו, וזה בטוח רק
בעמוד שהצהיר על עצמו ככזה. קריאה אחת לא מגודרת בעמוד החודש השאירה את
כל מופעי Chart.js על canvas מנותקים: הגרפים נעלמו, החיפוש מת, וכפתור
הניהול הפסיק להגיב באמצע הפעולה.

הבדיקות כאן לא מתארות את שני הבאגים — הן אוכפות את שני הכללים.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_TPL = _ROOT / "frontend/templates"
_JS = _ROOT / "frontend/static/js"

_INLINE_HANDLER = re.compile(r"\son[a-z]+\s*=\s*[\"']", re.I)


# ─── אין מטפלים בשורה ────────────────────────────────────────────────────────

@pytest.mark.parametrize("template", sorted(p.name for p in _TPL.glob("*.html")))
def test_no_template_uses_an_inline_event_handler(template):
    """ה-CSP חוסם אותם, והחסימה שקטה — אין שגיאת JS, רק כפתור שלא עושה
    כלום. זו הדרך היקרה ביותר לגלות."""
    html = (_TPL / template).read_text(encoding="utf-8")
    found = [m.group(0).strip() for m in _INLINE_HANDLER.finditer(html)]

    assert not found, (
        f"{template} מכיל מטפל בשורה {found} — ה-CSP יחסום אותו בשקט. "
        f"המקום למאזין הוא קובץ ה-JS של העמוד."
    )


def test_the_policy_that_makes_that_true_is_still_in_place():
    """בקרת-נגד: אם מישהו יתיר ‎unsafe-inline‎, הבדיקה למעלה תישאר ירוקה
    ותשמור על כלל שכבר לא נחוץ — בזמן שההגנה האמיתית נעלמה."""
    from backend.app import _CSP

    directives = dict(
        (d.split(" ", 1) + [""])[:2] if " " in d else (d, "")
        for d in (part.strip() for part in _CSP.split(";"))
    )
    script_src = directives.get("script-src", "")

    assert script_src == "'self'", f"script-src נפתח: {script_src!r}"
    assert "unsafe-inline" not in script_src


def test_the_waiting_screen_button_is_wired_before_the_early_exit():
    """מסך ההמתנה מוגש במקום האשף, ו-‎onboarding.js‎ יוצא מוקדם כשאין
    אשף. הכפתור היחיד שקיים שם חייב להיקשר לפני היציאה הזאת."""
    js = (_JS / "onboarding.js").read_text(encoding="utf-8")

    assert "waitingRefreshBtn" in js, "כפתור הרענון לא מחובר לשום מאזין"
    assert js.index("waitingRefreshBtn") < js.index("if (!step0) return;"), \
        "המאזין נרשם אחרי היציאה המוקדמת — כלומר לעולם לא, במסך שבו הוא נחוץ"


def test_the_wizard_has_a_way_out():
    """בלי זה מי שנרשם עם מייל שגוי, או הצטרף למשפחה הלא נכונה, תקוע:
    באשף אין ניווט, אין תפריט ואין אף קישור."""
    html = (_TPL / "onboarding.html").read_text(encoding="utf-8")

    assert "url_for('logout')" in html, "אין דרך החוצה מהאשף"


# ─── כל רענון רך מגודר ───────────────────────────────────────────────────────

def test_every_soft_reload_call_checks_the_page_opted_in():
    """הכלל, ולא המקרה. ‎softReload‎ מחליף את ‎main‎ כולו — קריאה בעמוד
    שלא הצהיר על עצמו כבטוח משאירה אחריה DOM חצי-מחובר."""
    js = (_JS / "transactions.js").read_text(encoding="utf-8")

    for match in re.finditer(r"window\.softReload\(", js):
        window = js[max(0, match.start() - 600):match.start()]
        assert "data-soft-reload" in window, (
            f"קריאה ל-softReload בתו {match.start()} בלי לבדוק "
            f"שהעמוד הצטרף לרענון רך"
        )


def test_the_month_page_repaints_its_charts_after_a_refresh():
    """העמוד הצטרף לרענון רך, אז כל canvas מוחלף. בלי ציור מחדש נשארות
    תוויות המרכז מרחפות מעל ריבועים ריקים."""
    js = (_JS / "month.js").read_text(encoding="utf-8")

    assert "function paint()" in js, "אין פונקציית ציור שאפשר להפעיל שוב"
    assert re.search(r"addEventListener\(\s*'sf:refreshed'\s*,\s*paint\s*\)", js), \
        "הגרפים לא נצבעים מחדש אחרי רענון רך"
    assert "destroy()" in js, \
        "מופעים קודמים לא נהרסים — new Chart על canvas תפוס זורק"


def test_the_month_page_rebuilds_its_legend_after_a_refresh():
    """המקרא נבנה ב-JS לתוך ‎<ul>‎ ריק. ה-HTML הטרי מביא אותו ריק שוב,
    אז בלי בנייה מחדש הכרטיס נשאר עם דונאט ובלי המספרים שהוא מצייר."""
    js = (_JS / "month.js").read_text(encoding="utf-8")

    assert re.search(r"addEventListener\(\s*'sf:refreshed'\s*,\s*buildOverviewLegend\s*\)", js)
