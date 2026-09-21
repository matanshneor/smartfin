"""
המספר הראשי בדשבורד לא התעדכן, ומשפחה חדשה נשארה עם "בואו נתחיל".

הרענון הרך החליף ‎main.main-content‎ בלבד, וה-hero הוא **אח** שלו
ב-base.html ולא בן. כך ש"נשאר בעו״ש החודש" — המספר שכל האפליקציה
קיימת בשבילו — נשאר תקוע אחרי כל הוספה ועריכה, עד רענון מלא.

ולמשפחה חדשה זה גרוע במיוחד: ה-hero מציג "לחצו על + כדי להוסיף את
העסקה הראשונה שלכם **ולראות כאן את היתרה שלכם**", והמשפט הזה נשאר על
המסך מעל העסקה שהרגע נוספה.

ובאותו מסך, באג שני: בדשבורד ריק אין ‎.transactions-list‎ בכלל, אבל
‎closeModal()‎ רץ בכל מקרה — אז כישלון שמירה נכתב לתוך חלון סגור.
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


def _read(p):
    return p.read_text(encoding="utf-8")


# ─── ה-hero באמת מוחלף ──────────────────────────────────────────────────────

def test_the_hero_is_a_sibling_of_main_not_a_child():
    """זה השורש. אם המבנה ישתנה, ההנחה למטה כבר לא נכונה."""
    base = _read(_TPL / "base.html")

    assert base.index('<header class="page-hero">') < base.index('<main class="main-content"')
    assert "</header>" in base[:base.index('<main class="main-content"')]


def test_the_soft_reload_replaces_both_regions():
    core = _read(_JS / "core.js")

    assert "'header.page-hero'" in core
    assert "'main.main-content'" in core


def test_a_partial_swap_falls_back_to_a_full_reload():
    """hero חדש מעל גוף ישן גרוע מרענון מלא. לכן כל האזורים נאספים
    לפני שנוגעים באחד מהם."""
    core = _read(_JS / "core.js")
    block = core[core.index("window.softReload = function"):]
    block = block[:block.index("\n};")]

    assert "pairs.some(p => !p[0] || !p[1])" in block
    assert block.index("pairs.some") < block.index("pairs.forEach")
    assert "window.location.reload()" in block


def test_the_numbers_animate_again_after_a_refresh():
    """ה-count-up רץ רק ב-DOMContentLoaded, אז אחרי רענון רך המספרים
    החדשים הופיעו בלי אנימציה — דווקא ברגע שבו מחכים להם."""
    motion = _read(_JS / "motion.js")

    assert "window.addEventListener('sf:refreshed'" in motion
    block = motion[motion.index("window.addEventListener('sf:refreshed'"):]
    assert "runCountUps()" in block
    assert "runStagger()" not in block, "אנימציית כניסה על כל עדכון היא רעש"


# ─── התנהגות אמיתית, מורצת ב-node ───────────────────────────────────────────

_HARNESS = r"""
const fs = require('fs');
const g = globalThis;

const replaced = [];
function el(sel, ok) {
    return ok ? { sel, replaceWith(fresh) { replaced.push(fresh.sel); } } : null;
}

// העמוד החי מכיל את שני האזורים; התשובה מהשרת — לפי הארגומנט
const stub = () => ({
    style: {}, dataset: {}, textContent: '', innerHTML: '',
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    addEventListener() {}, appendChild() {}, focus() {}, setAttribute() {},
    querySelector: () => null, querySelectorAll: () => [],
});

const liveHas   = new Set(['header.page-hero', 'main.main-content']);
const freshHas  = new Set(JSON.parse(process.argv[2]));

// core.js עושה עוד דברים בטעינה (toast, דיאלוג אישור) — כולם
// מקבלים null ומדלגים על עצמם בשקט, בדיוק כמו בעמוד בלי הרכיבים.
g.document = {
    querySelector: (sel) => el(sel, liveHas.has(sel)),
    querySelectorAll: () => [],
    // core.js מניח שרכיבי הדיאלוג קיימים ולא בודק null, אז מחזירים
    // אובייקט אדיש במקום null
    getElementById: (id) => (id === 'sf-page-data'
        ? Object.assign(stub(), { textContent: '{}' })
        : stub()),
    createElement: () => stub(),
    addEventListener() {},
    body: { appendChild() {}, style: {} },
};
g.window = g;
g.CustomEvent = class { constructor(t) { this.type = t; } };
let reloaded = false;
g.location = { href: 'http://x/', reload() { reloaded = true; } };
g.dispatchEvent = () => {};
g.addEventListener = () => {};
g.matchMedia = () => ({ matches: false });
// ‎sessionStorage‎/‎localStorage‎ קיימים כגלובלי רק מ-node 24. ב-CI רץ
// node 22, ושם הם נעדרים — וזה מה שהפיל את הבדיקה הזאת בפעם הראשונה.
g.sessionStorage = { getItem: () => null, setItem() {}, removeItem() {} };
g.localStorage   = { getItem: () => null, setItem() {}, removeItem() {} };
g.requestAnimationFrame = (fn) => fn(0);
g.DOMParser = class {
    parseFromString() { return { querySelector: (sel) => el(sel, freshHas.has(sel)) }; }
};
g.fetch = () => Promise.resolve({ ok: true, text: () => Promise.resolve('<html></html>') });

(0, eval)(fs.readFileSync(process.argv[3], 'utf8'));

g.softReload().then(function () {
    console.log(JSON.stringify({ replaced, reloaded }));
});
"""


def _run(fresh_regions):
    node = shutil.which("node")
    if not node:
        pytest.skip("node לא מותקן")
    harness = _ROOT / "tests" / "_hero_harness.js"
    harness.write_text(_HARNESS, encoding="utf-8")
    try:
        out = subprocess.run(
            [node, str(harness), json.dumps(fresh_regions), str(_JS / "core.js")],
            capture_output=True, text=True, timeout=30)
    finally:
        harness.unlink(missing_ok=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_both_regions_are_actually_swapped():
    res = _run(["header.page-hero", "main.main-content"])

    assert res["replaced"] == ["header.page-hero", "main.main-content"]
    assert res["reloaded"] is False


def test_a_missing_region_swaps_nothing_and_reloads():
    """בקרת-נגד: חצי החלפה משאירה מסך שסותר את עצמו."""
    res = _run(["main.main-content"])       # אין hero בתשובה מהשרת

    assert res["replaced"] == [], "הוחלף אזור אחד למרות שהשני חסר"
    assert res["reloaded"] is True


# ─── העסקה הראשונה ──────────────────────────────────────────────────────────

def _inside_braces(text, opener):
    """התוכן שבין הסוגריים של הבלוק שמתחיל ב-‎opener‎.

    השוואת מיקומים לא מספיקה כאן: שורה שיושבת **אחרי** ‎if (list) {‎
    אבל **מחוץ** לסוגריים שלו עוברת אותה — וזה בדיוק המצב השבור.
    אומת בבדיקת מוטציה: הגרסה הקודמת של הבדיקה הזאת לא נפלה עליו."""
    i = text.index(opener) + len(opener)
    depth, j = 1, i
    while depth:
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
        j += 1
    return text[i:j - 1]


def test_the_modal_only_closes_when_there_is_a_row_to_show():
    """בדשבורד ריק אין ‎.transactions-list‎, אז לא נוצרה שורה זמנית —
    אבל החלון נסגר בכל זאת, וכל הודעת שגיאה נכתבה לתוך חלון סגור."""
    js = _read(_JS / "transactions.js")
    block = js[js.index("let placeholderRow = null;"):]
    block = block[:block.index("const url    = editId")]

    guarded = _inside_braces(block, "if (list) {")

    assert "closeModal();" in guarded, "closeModal מחוץ לתנאי"
    # וגם הכפתור לא משתחרר כל עוד החלון פתוח ומחכה לשרת
    assert "setSubmitBusy(false);" in guarded
    # ובקרת-נגד לכל הבדיקה: מחוץ לתנאי לא נשארה אף אחת מהן
    outside = block.replace(guarded, "")
    assert "closeModal();" not in outside


def test_the_empty_dashboard_really_has_no_list():
    """השורש של ב2 — אם התבנית תתחיל לרנדר רשימה ריקה, התנאי למעלה
    כבר לא מגן על כלום."""
    index = _read(_TPL / "index.html")
    block = index[index.index("transactions-list") - 400:index.index("transactions-list")]

    assert "{% if transactions %}" in block


# ─── core.js לא נופל כשאין אחסון ────────────────────────────────────────────

def test_storage_access_cannot_take_the_whole_file_down():
    """‎sessionStorage.getItem‎ רץ בטעינת הקובץ. חריגה שם — גלישה
    פרטית, אחסון חסום, או סביבה בלי Web Storage — הפילה את **כל**
    core.js: אין toast, אין דיאלוג אישור, אין רענון רך.

    ככה זה התגלה: ב-CI רץ node 22, שאין בו ‎sessionStorage‎ כגלובלי,
    והבדיקות כאן נפלו על משהו שלא היה קשור אליהן."""
    core = _read(_JS / "core.js")

    for call in ("sessionStorage.getItem", "sessionStorage.removeItem",
                 "localStorage.getItem"):
        i = core.index(call)
        before = core[max(0, i - 300):i]
        assert "try {" in before, f"{call} בלי try"


def test_the_harness_does_not_depend_on_the_node_version():
    """הארנס עצמו מספק את מה ש-core.js נוגע בו בטעינה, כדי שהבדיקה
    תיפול על הקוד שהיא בודקת ולא על סביבת ההרצה."""
    src = _HARNESS

    assert "g.sessionStorage" in src
    assert "g.localStorage" in src
