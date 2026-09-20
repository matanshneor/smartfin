"""
כשל בטעינת Chart.js השבית את כל העמוד, לא רק את הגרפים.

שמונה שורות של ‎Chart.defaults‎ ישבו בראש הבלוק שהחזיק גם את פתיחת
הקטגוריות, את החיפוש בעסקאות ואת מקש Enter. אם הספרייה לא הגיעה —
חוסם, רשת גרועה, קובץ פגום במטמון — השורה הראשונה זרקה ReferenceError
והשאר לא רץ מעולם. העמוד נראה תקין לגמרי ופשוט לא הגיב ללחיצות, וזה
הבלבול הגרוע ביותר: אין אפילו מה לדווח עליו.

וזה לא היה תיאורטי. ‎month.html‎ טוענת את הספרייה רק כשיש עסקאות, אז
כל חודש ריק — כולל הראשון של כל משפחה חדשה — הרים את השגיאה הזאת.

אותן שמונה שורות היו משוכפלות בשלושה קבצים, כלומר גם הבאג היה משולש.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_JS   = _ROOT / "frontend/static/js"
_TPL  = _ROOT / "frontend/templates"

_CHART_PAGES = ["month", "months", "project-detail"]


def _read(p):
    return p.read_text(encoding="utf-8")


# ─── הכלל במקום אחד ─────────────────────────────────────────────────────────

def test_the_chart_defaults_live_in_exactly_one_file():
    """שלושה עותקים היו גם שלושה באגים."""
    owners = [f.name for f in _JS.glob("*.js") if "Chart.defaults" in _read(f)]
    assert owners == ["chart-setup.js"], f"Chart.defaults נמצא ב: {owners}"


@pytest.mark.parametrize("page", _CHART_PAGES)
def test_every_chart_block_is_behind_the_flag(page):
    js = _read(_JS / f"{page}.js")
    assert "if (!window.sfCharts.ready) return;" in js, \
        f"{page}.js מצייר בלי לבדוק שיש ספרייה"


@pytest.mark.parametrize("page", _CHART_PAGES)
def test_the_drawing_sits_after_the_guard_and_not_before(page):
    """בקרת-נגד: דגל שנבדק אחרי הציור לא שווה כלום."""
    js = _read(_JS / f"{page}.js")
    assert js.index("if (!window.sfCharts.ready) return;") < js.index("new Chart("), \
        f"{page}.js מצייר לפני הבדיקה"


# ─── העמודים טוענים את הקובץ ────────────────────────────────────────────────

@pytest.mark.parametrize("page", ["month.html", "months.html", "project_detail.html"])
def test_every_page_with_charts_loads_the_setup(page):
    assert "js/chart-setup.js" in _read(_TPL / page)


def test_the_month_page_loads_the_setup_even_when_it_skips_the_library():
    """זה הלב: הספרייה נטענת רק ‎{% if month_transactions %}‎, וחודש ריק
    הוא בדיוק המקרה שבו מישהו צריך להגיד לשאר הקוד "אין גרפים"."""
    html = _read(_TPL / "month.html")
    block = html[html.index("{% block scripts %}"):]
    setup_at = block.index("js/chart-setup.js")
    endif_at = block.index("{% endif %}")
    assert setup_at > endif_at, "chart-setup.js נטען בתוך התנאי — בחודש ריק הוא לא ירוץ"


# ─── מה קורה בפועל בלי הספרייה ──────────────────────────────────────────────

_HARNESS = r"""
const fs = require('fs');
const listeners = [];
const g = globalThis;

g.document = {
    documentElement: { style: { setProperty() {} } },
    addEventListener: (type) => listeners.push(type),
    getElementById:   () => null,
    querySelectorAll: () => [],
};
g.window = g;
g.sfData = () => ({
    summary:   { expense: 1950, savings: 8000, income: 11527 },
    expense:   [],
    members:   [],
    trend:     [],
    breakdown: {},
});

for (const f of process.argv.slice(2)) {
    (0, eval)(fs.readFileSync(f, 'utf8'));
}
console.log(JSON.stringify({ listeners, ready: g.sfCharts.ready }));
"""


def _run_node(harness_js, *files):
    """מריצה את קבצי ה-JS האמיתיים תחת DOM מזויף, ומחזירה מה שהם עשו."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node לא מותקן")
    harness = _ROOT / "tests" / "_chart_harness.js"
    harness.write_text(harness_js, encoding="utf-8")
    try:
        out = subprocess.run(
            [node, str(harness)] + [str(_JS / f) for f in files],
            capture_output=True, text=True, timeout=30,
        )
    finally:
        harness.unlink(missing_ok=True)
    assert out.returncode == 0, f"הקוד קרס:\n{out.stderr[:800]}"
    return json.loads(out.stdout)


def _run_without_chart_js(*files):
    return _run_node(_HARNESS, *files)


def test_the_month_page_still_listens_for_clicks_without_the_library():
    """הבדיקה שהייתה נכשלת לפני התיקון: בלי Chart גלובלי, הקובץ קרס
    לפני שהספיק לרשום האזנה אחת."""
    result = _run_without_chart_js("chart-setup.js", "month.js")

    assert result["ready"] is False
    assert "click" in result["listeners"], "פתיחת קטגוריה לא נרשמה"
    assert "keydown" in result["listeners"], "מקש Enter לא נרשם"


def test_the_project_page_still_listens_for_clicks_without_the_library():
    result = _run_without_chart_js("chart-setup.js", "project-detail.js")

    assert result["ready"] is False
    assert "click" in result["listeners"]
    assert "keydown" in result["listeners"]


def test_the_months_page_survives_without_the_library():
    result = _run_without_chart_js("chart-setup.js", "months.js")

    assert result["ready"] is False


def test_the_legend_colours_are_set_even_without_the_library():
    """חלק מהמקראות מרונדרות בשרת ונצבעות מ-‎--chart-color-N‎. אם הן
    נקבעות רק ליד הגרפים, מקרא שלם מאבד את הצבעים שלו."""
    setup = _read(_JS / "chart-setup.js")
    guard_at = setup.index("if (typeof Chart === 'undefined')")
    assert setup.index("--chart-color-") < guard_at, \
        "צבעי המקרא נקבעים רק כשיש ספרייה"


# ─── מה המשתמש רואה במקום הגרף ──────────────────────────────────────────────

def test_the_empty_chart_says_the_numbers_are_still_right():
    """קנבס ריק נראה כמו תקלה, ומשתמש שרואה תקלה בעמוד כספי מפסיק
    לסמוך על המספרים שלידה."""
    setup = _read(_JS / "chart-setup.js")

    assert "הגרף לא נטען" in setup
    assert "המספרים עצמם מעודכנים ונכונים" in setup


def test_the_doughnut_centre_is_pulled_back_into_flow():
    """המספר שבמרכז הדונאט ממוקם אבסולוטית מעל הקנבס. בלי הקנבס אין לו
    גובה להתמקם בתוכו, והוא היה נופל על הטקסט."""
    css = _read(_ROOT / "frontend/static/css/style.css")
    block = css[css.index(".chart-unavailable"):css.index(".chart-unavailable") + 400]

    assert "position: static" in block


# ─── בקרת-נגד: כשהספרייה כן שם, הכול מצויר כמו קודם ─────────────────────────

_WITH_CHART = r"""
const fs = require('fs');
const g = globalThis;
const drawn = [], legend = [];
const els = {};
const el = (id) => els[id] || (els[id] = { id, appendChild() {}, setAttribute() {}, addEventListener() {} });

g.Chart = function (ctx, cfg) {
    drawn.push({ el: ctx.id, type: cfg.type, points: cfg.data.datasets[0].data.length });
};
g.Chart.defaults = { font: {}, color: null, animation: {},
                     plugins: { legend: {}, tooltip: {} } };

g.document = {
    documentElement: { style: { setProperty() {} } },
    addEventListener() {},
    createElement: () => ({ className: '', innerHTML: '' }),
    querySelectorAll: () => [],
    getElementById: (id) =>
        (id === 'monthStrip' || id === 'txSearch') ? null :
        (id === 'overviewLegend' ? { appendChild: (li) => legend.push(li.innerHTML) } : el(id)),
};
g.window = g;
g.sfData = () => ({
    summary: { expense: 1950, savings: 8000, income: 11527 },
    expense: [{ name: 'סופר', total: 650, pct: 33 }, { name: 'דלק', total: 1300, pct: 67 }],
    members: [{ type: 'expense', label: 'הוצאות',
                rows: [{ name: 'מתן', expense: 100, color: '#A67C00' }] }],
});

for (const f of process.argv.slice(2)) (0, eval)(fs.readFileSync(f, 'utf8'));
console.log(JSON.stringify({ drawn, legend: legend.length }));
"""


def test_the_month_charts_are_still_drawn_when_the_library_is_there():
    """הפיצול לשני בלוקים היה יכול להשאיר גרף מאחור בלי שאף בדיקה
    תרגיש. שלושת הגרפים והמקרא — בדיוק כמו לפניו."""
    result = _run_node(_WITH_CHART, "chart-setup.js", "month.js")

    assert result["drawn"] == [
        {"el": "overviewChart",        "type": "doughnut", "points": 2},
        {"el": "expenseChart",         "type": "doughnut", "points": 2},
        {"el": "membersChart-expense", "type": "bar",      "points": 1},
    ]
    assert result["legend"] == 2, "המקרא של לאן הלך הכסף לא נבנה"
