"""
בדיקות לרענון הרך.

כל פעולה באפליקציה הסתיימה ב-location.reload(). הוספת עסקה עלתה בערך
שתי שניות מהקשה עד מסך יציב: השהיה מכוונת של 380ms כדי שהצליל יסתיים,
סבב לשרת, ניתוח מחדש של 99KB CSS ו-77KB JS, ואנימציית ספירה של שנייה
על המספר שבדיוק רצית לראות. בדרך נמחקה גם השורה הזמנית שכבר הוצגה,
וגם מיקום הגלילה.

הסיכון בשינוי כזה הוא לא המהירות אלא מה שנשבר בשקט: עמוד עם מופעי
Chart.js או עם האזנות ישירות לא שורד החלפת DOM. לכן ההצטרפות מפורשת
לכל עמוד, ומי שלא הצטרף ממשיך לקבל רענון מלא — ההתנהגות הקיימת.
"""
from pathlib import Path

import re

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_TPL  = _ROOT / "frontend/templates"
_JS   = _ROOT / "frontend/static/js"


def _read(path):
    return path.read_text(encoding="utf-8")


# ─── מי מצטרף ומי לא ─────────────────────────────────────────────────────────

def test_the_dashboard_opts_in():
    assert "{% block soft_reload %} data-soft-reload{% endblock %}" in _read(_TPL / "index.html")


# הכלל הישן היה "עמוד עם גרפים לא מצטרף", כי החלפת ה-DOM משאירה מופעי
# Chart.js תלויים על אלמנטים שכבר לא במסמך. זה נכון — אבל זו תוצאה ולא
# חוק: עמוד שמצייר מחדש ב-‎sf:refreshed‎ בטוח לגמרי. עמוד החודש עשה בדיוק
# את זה, והכלל הישן הפך אותו לכישלון.
#
# הכלל עכשיו מנוסח על התכונה עצמה: מי שמצטרף חייב לדעת לצייר מחדש.
@pytest.mark.parametrize("page,script", [
    ("month.html", "month.js"),
    ("months.html", "months.js"),
    ("project_detail.html", "project-detail.js"),
])
def test_a_page_with_charts_that_opts_in_repaints_them(page, script):
    if "data-soft-reload" not in _read(_TPL / page):
        pytest.skip(f"{page} אינו מצטרף לרענון רך")

    js = _read(_ROOT / "frontend/static/js" / script)
    assert "sf:refreshed" in js, (
        f"{page} מצטרף לרענון רך אבל {script} לא מצייר מחדש — "
        f"הגרפים יישארו על canvas מנותקים"
    )


def test_a_page_that_opts_in_binds_nothing_directly_to_an_element(page="month.html",
                                                                  script="month.js"):
    """‎softReload‎ מחליף את ‎main‎ כולו. כל ‎getElementById(...).addEventListener‎
    שרץ בטעינה מצביע אחר כך על אלמנט מנותק, והפקד נראה חי ומת בלחיצה."""
    js = _read(_ROOT / "frontend/static/js" / script)

    direct = re.findall(r"document\.getElementById\([^)]+\)\.addEventListener", js)
    assert not direct, f"{script} נקשר ישירות: {direct}"


def test_the_base_template_defaults_to_not_opting_in():
    """ברירת המחדל היא ההתנהגות הקיימת. עמוד חדש לא נשבר בשקט."""
    base = _read(_TPL / "base.html")

    assert '<main class="main-content"{% block soft_reload %}{% endblock %}>' in base


# ─── ההתנהגות ─────────────────────────────────────────────────────────────────

def test_the_caller_falls_back_to_a_full_reload_when_not_opted_in():
    js = _read(_JS / "transactions.js")
    block = js[js.index("function finish()"):][:900]

    assert "main[data-soft-reload]" in block, "הרענון הרך רץ בלי לבדוק הצטרפות"
    assert "window.location.reload()" in block, "אין נפילה חזרה לרענון מלא"


def test_a_failed_soft_reload_falls_back_rather_than_leaving_a_stale_screen():
    """במקרה הגרוע ההתנהגות זהה להיום — זה מה שהופך את השינוי לבטוח."""
    js = _read(_JS / "core.js")
    block = js[js.index("window.softReload ="):]

    assert ".catch(" in block and "window.location.reload()" in block


def test_the_soft_reload_does_not_replay_the_count_up_animation():
    """ספירה מ-0 אחרי עדכון גורמת למספר לקפוץ אחורה מול העיניים, וה-HTML
    הטרי ממילא מכיל את הערך הסופי כטקסט."""
    js = _read(_JS / "core.js")
    block = js[js.index("window.softReload ="):]

    assert "runCountUps" not in block
    assert "anim-rise" not in block


def test_jinja_stays_the_only_renderer():
    """מושכים את אותו עמוד ולוקחים ממנו HTML מוכן. שכפול לוגיקת תצוגה
    ב-JS הוא בדיוק מקור הבאגים שהשינוי הזה נמנע ממנו."""
    js = _read(_JS / "core.js")
    block = js[js.index("window.softReload ="):]

    assert "fetch(window.location.href" in block
    assert "DOMParser" in block
