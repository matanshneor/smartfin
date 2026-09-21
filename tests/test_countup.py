"""
אנימציית הספירה תמיד רצה מאפס.

אחרי הוספת הוצאה של ₪100 המשתמש ראה את "נשאר בעו״ש" מטפס מאפס עד
הסכום החדש — אנימציה של שנייה שלמה שלא מספרת לו כלום. מה שמעניין הוא
**מה השתנה**: שהיתרה ירדה ב-₪100. מתן ביקש את זה אחרי שראה את הרענון
הרך עובד.

בטעינה ראשונה אין ערך קודם, ושם אפס הוא הנכון — זה הרושם הראשון,
לא עדכון.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_JS   = _ROOT / "frontend/static/js"

_HARNESS = r"""
const fs = require('fs'), g = globalThis;
const reduce = process.argv[3] === 'reduce';
let handlers = {};
const frames = [];

function makeEl(cls, value, prefix) {
    return { className: cls, dataset: { countup: String(value),
             ...(prefix ? { prefix } : {}) },
             set textContent(v) { frames.push(v); }, get textContent() { return ''; },
             style: {}, classList: { add() {}, toggle() {} } };
}

let current = [];
g.document = {
    querySelectorAll: (s) => s === '[data-countup]' ? current : [],
    addEventListener: (t, fn) => { handlers[t] = fn; },
};
g.window = g;
g.addEventListener = (t, fn) => { handlers[t] = fn; };
g.matchMedia = () => ({ matches: reduce });
// שעון אחד לשניהם. ‎performance.now‎ ו-‎requestAnimationFrame‎ חייבים
// לדבר באותה יחידה — אחרת ‎now - start‎ שלילי, ההתקדמות לא מגיעה ל-1,
// והלולאה רצה לנצח.
let clock = 0;
g.performance = { now: () => clock };
// מתקדמים ברבע שנייה כל פריים: מספיק כדי לראות התקדמות אמיתית,
// ומגיע ל-1000ms (סוף האנימציה) אחרי ארבעה.
g.requestAnimationFrame = (fn) => { clock += 250; setTimeout(() => fn(clock), 0); };

(0, eval)(fs.readFileSync(process.argv[2], 'utf8'));

const steps = JSON.parse(process.argv[4]);   // [[value, prefix], ...]
(function next(i) {
    if (i >= steps.length) {
        console.log(JSON.stringify({ frames }));
        return;
    }
    current = [makeEl('hero-amount', steps[i][0], steps[i][1] || '')];
    frames.push('--');
    if (i === 0) handlers.DOMContentLoaded();
    else handlers['sf:refreshed']();
    setTimeout(() => next(i + 1), 60);
})(0);
"""


def _run(steps, reduce=False):
    node = shutil.which("node")
    if not node:
        pytest.skip("node לא מותקן")
    h = _ROOT / "tests" / "_countup_harness.js"
    h.write_text(_HARNESS, encoding="utf-8")
    try:
        out = subprocess.run([node, str(h), str(_JS / "motion.js"),
                              "reduce" if reduce else "normal", json.dumps(steps)],
                             capture_output=True, text=True, timeout=30)
    finally:
        h.unlink(missing_ok=True)
    assert out.returncode == 0, out.stderr[:800]
    frames = json.loads(out.stdout.strip().splitlines()[-1])["frames"]
    # מפצלים לקבוצות לפי הסמן '--'
    groups, cur = [], None
    for f in frames:
        if f == "--":
            if cur is not None:
                groups.append(cur)
            cur = []
        else:
            cur.append(f)
    if cur is not None:
        groups.append(cur)
    return groups


def _num(text):
    return int(text.replace("₪", "").replace(",", "").replace("-", "") or 0)


# ─── ההתנהגות שביקש מתן ─────────────────────────────────────────────────────

def test_the_second_render_never_goes_near_zero():
    """הלב. ₪5,000 ואז ₪4,900 — כל האנימציה נעה בין שני הערכים, ולא
    צונחת לאפס ומטפסת בחזרה.

    נבדק על כל הפריימים ולא על הראשון בלבד: הראשון שנדגם הוא כבר
    אחרי רבע שנייה של האצה, ולא נקודת ההתחלה עצמה."""
    first, second = _run([[5000, ""], [4900, ""]])

    values = [_num(f) for f in second]
    assert min(values) >= 4900, f"ירד עד {min(values)} — כלומר התחיל מאפס"
    assert max(values) <= 5000
    assert values[-1] == 4900


def test_the_first_render_still_climbs_from_zero():
    """בקרת-נגד: זה הרושם הראשון, לא עדכון — ושם אפס הוא הנכון."""
    first, = _run([[5000, ""]])

    values = [_num(f) for f in first]
    assert values[0] < 5000 * 0.8, f"התחיל מ-{values[0]} — לא נראה כמו טיפוס מאפס"
    assert values[-1] == 5000


def test_a_number_that_did_not_change_does_not_animate():
    """אנימציה מערך לעצמו היא שנייה של כלום. קורה בכל רענון שלא נגע
    במספר הזה — למשל הוספת עסקת פרויקט, שלא נכנסת למאזן."""
    first, second = _run([[5000, ""], [5000, ""]])

    assert second == ["₪5,000"], f"רצו {len(second)} פריימים במקום אחד"


def test_flipping_between_surplus_and_deficit_starts_from_zero():
    """המספר מוצג בערך מוחלט עם קידומת. מעבר ישיר בין שני ערכים
    מוחלטים היה מציג סכומי ביניים עם הסימן ההפוך — "-₪250" בדרך
    מעודף של ₪300 לגירעון של ₪200."""
    first, second = _run([[300, ""], [200, "-"]])

    values = [_num(f) for f in second]
    assert max(values) <= 200, f"הגיע עד {max(values)} — המשיך מהערך הקודם"
    assert second[-1] == "-₪200"
    assert all(f.startswith("-") for f in second), "הסימן לא עקבי לאורך האנימציה"


def test_reduced_motion_still_skips_everything():
    """בקרת-נגד: ההעדפה הזאת גוברת על הכול, גם על ההתנהגות החדשה."""
    first, second = _run([[5000, ""], [4900, ""]], reduce=True)

    assert first == ["₪5,000"]
    assert second == ["₪4,900"]
