"""
שדה התקציב לא שמר כלום — אף פעם.

‎savePrefs‎ הוגדר בתוך הבלוק של "העדפות משפחה", וקוד תקציבי הקטגוריות
יושב בבלוק אחר לגמרי. שני תחומים נפרדים, כלומר הפונקציה פשוט לא קיימת
שם: כל הקלדה בשדה התקציב זרקה ‎ReferenceError: savePrefs is not defined‎
מתוך ‎setTimeout‎ — בלי הודעה, בלי שגיאה על המסך, בלי שום סימן. מתן דיווח
על זה במילים "כאילו לא נשמר", וזה היה מדויק: שום בקשה לא יצאה.

זה החצי השני של אותה תכונה. הראשון — ‎apply_budgets‎ שחיפשה ‎category_id‎
שלא היה בשורות הפילוח — תוקן קודם. שני החצאים היו שבורים במקביל, ולכן
התכונה לא עבדה מהיום ששוחררה.

**למה שום בדיקה לא תפסה:** הבדיקות חיפשו את המחרוזת ‎savePrefs({ limits:‎
בקוד המקור, והיא הייתה שם. נוכחות בטקסט אינה נגישות בתחום. הבדיקות כאן
מריצות את הקובץ האמיתי ובודקות שבקשה באמת יוצאת.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_JS   = _ROOT / "frontend/static/js"

_CAT = "c1"

# DOM מינימלי של שדות התקציב של קטגוריה אחת, כמו שהם בעמוד ההגדרות.
_HARNESS = r"""
const fs = require('fs'), g = globalThis;
const listeners = {};
const CAT = 'c1';

const amountEl = { classList: { contains: c => c === 'budget-amount' },
                   dataset: { id: CAT, saved: '' }, value: '500', focus() {},
                   closest: (s) => s === '.budget-amount' ? amountEl
                                 : (s === '.cat-budget-edit' ? editEl : null) };
const enabledEl = { checked: true, dataset: { id: CAT },
                    closest: (s) => s === '.cat-budget-edit' ? editEl : null,
                    classList: { contains: () => false } };
const fieldsEl = { hidden: false };
const saveBtn  = { disabled: false, textContent: 'שמור', dataset: { id: CAT },
                   closest: (s) => s === '.budget-save' ? saveBtn
                                 : (s === '.cat-budget-edit' ? editEl : null) };
const editEl = { querySelector: (s) => ({
    '.budget-enabled': enabledEl, '.budget-amount': amountEl,
    '.budget-save': saveBtn, '.cat-budget-fields': fieldsEl }[s] || null) };

const stub = () => ({ style:{}, dataset:{}, textContent:'', innerHTML:'', value:'',
    checked:false, hidden:false, classList:{add(){},remove(){},toggle(){},contains:()=>false},
    addEventListener(){}, appendChild(){}, focus(){}, setAttribute(){},
    closest:()=>stub(), querySelector:()=>stub(), querySelectorAll:()=>[] });

g.document = {
    getElementById: () => stub(),
    querySelector: (s) => s.startsWith('.budget-enabled[data-id') ? enabledEl : stub(),
    querySelectorAll: () => [],
    createElement: () => stub(),
    addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
    body: { appendChild() {}, style: {} },
};
g.window = g; g.location = { href:'http://x/', reload(){}, pathname:'/settings' };
g.sessionStorage = { getItem:()=>null, setItem(){}, removeItem(){} };
g.localStorage   = { getItem:()=>null, setItem(){}, removeItem(){} };
const sent = [], errors = [];
g.fetch = (url, opt) => { sent.push({ url, body: opt && opt.body });
    return Promise.resolve({ ok:true, json:()=>Promise.resolve({ settings:{} }) }); };
g.showToast=()=>{}; g.appConfirm=()=>Promise.resolve(false); g.sfNetError=()=>'net';
g.sfData=()=>({}); g.softReload=()=>Promise.resolve(); g.requestAnimationFrame=fn=>fn(0);
g.matchMedia=()=>({matches:false}); g.SF_PAGE_DATA={}; g.confirm=()=>false;

(0, eval)(fs.readFileSync(process.argv[2], 'utf8'));

// הקלדה בשדה הסכום, ואז לחיצה על "שמור"
(listeners.input || []).forEach(fn => { try { fn({ target: amountEl }); }
                                        catch (e) { errors.push(String(e)); } });
if (process.argv[3] !== 'no-click') {
    (listeners.click || []).forEach(fn => { try { fn({ target: saveBtn }); }
                                            catch (e) { errors.push(String(e)); } });
}

// ההשהיה לפני השמירה היא 600ms
setTimeout(() => {
    console.log(JSON.stringify({ listeners: (listeners.input||[]).length, sent, errors }));
}, 900);

process.on('uncaughtException', (e) => {
    console.log(JSON.stringify({ listeners: (listeners.input||[]).length, sent,
                                 errors: errors.concat(String(e)) }));
    process.exit(0);
});
"""


def _run(click=True):
    node = shutil.which("node")
    if not node:
        pytest.skip("node לא מותקן")
    harness = _ROOT / "tests" / "_budget_harness.js"
    harness.write_text(_HARNESS, encoding="utf-8")
    try:
        out = subprocess.run([node, str(harness), str(_JS / "settings.js"),
                              "click" if click else "no-click"],
                             capture_output=True, text=True, timeout=30)
    finally:
        harness.unlink(missing_ok=True)
    assert out.stdout.strip(), f"הארנס לא הדפיס כלום:\n{out.stderr}"
    return json.loads(out.stdout.strip().splitlines()[-1])


# ─── הבדיקה שהייתה חסרה ─────────────────────────────────────────────────────

def test_saving_a_budget_actually_sends_it_to_the_server():
    """הלב. עד היום זה זרק ReferenceError ולא יצאה שום בקשה."""
    res = _run()

    assert res["errors"] == [], f"נזרקה שגיאה: {res['errors']}"
    assert len(res["sent"]) == 1, "לא נשלחה בקשה לשרת"


def test_the_request_goes_to_the_right_place_with_the_right_shape():
    res = _run()
    req = res["sent"][0]

    assert req["url"] == "/api/family/settings"
    assert json.loads(req["body"]) == {"limits": {_CAT: {"amount": 500}}}


def test_the_listener_is_registered_at_all():
    """בקרת-נגד: אם הקובץ קורס בטעינה לפני בלוק התקציב, אין מאזין."""
    assert _run()["listeners"] == 1


# ─── שמירה מפורשת, ובלי שאלה מיותרת ─────────────────────────────────────────

def test_typing_alone_saves_nothing():
    """סכום נכתב ספרה-ספרה. שמירה על כל הקשה שומרת גם את "2" ואת "20"
    בדרך ל-"200" — כלומר תקציב שגוי, שנשמר, שלוש פעמים."""
    res = _run(click=False)

    assert res["sent"] == [], "נשמר בלי שנלחץ שמור"


def test_there_is_no_separate_alert_question():
    """הייתה תיבה שנייה, "התרע בחריגה". בפועל זו הבחנה בלי הבדל: מי
    שטרח להגדיר תקציב רוצה לדעת כשחרג ממנו."""
    html = (_ROOT / "frontend/templates/settings.html").read_text(encoding="utf-8")
    js   = (_JS / "settings.js").read_text(encoding="utf-8")

    assert "budget-alert" not in html
    assert "budget-alert" not in js


def test_the_server_still_alerts_when_nothing_was_asked():
    """מרגע שהתיבה ירדה, הברירה חייבת להיות "כן" — אחרת התקציב הופך
    למספר על המסך בלי שום התרעה."""
    from backend import supabase_config as db

    budget = db.category_budget({"limits": {_CAT: {"amount": 500}}}, _CAT)

    assert budget["alert"] is True


# ─── הכלל, ולא המקרה ────────────────────────────────────────────────────────

def test_no_function_is_called_from_outside_the_block_that_defines_it():
    """זה הכלל שהבאג הפר. בקובץ יש כמה בלוקים עצמאיים, וקריאה לפונקציה
    של בלוק אחר עוברת בשקט את כל הבדיקות הטקסטואליות — ונכשלת בזמן ריצה,
    בתוך callback שאיש לא צופה בו."""
    import re

    for path in sorted(_JS.glob("*.js")):
        src = path.read_text(encoding="utf-8")

        tops, stack = [], []
        for i, ch in enumerate(src):
            if ch == "{":
                stack.append(i)
            elif ch == "}":
                if len(stack) == 1:
                    tops.append((stack[0], i))
                if stack:
                    stack.pop()
        if len(tops) < 2:
            continue

        defined = {}
        for m in re.finditer(r"^\s{4,}function ([A-Za-z_$][\w$]*)\s*\(", src, re.M):
            for a, b in tops:
                if a < m.start() < b:
                    defined[m.group(1)] = (a, b)
                    break

        for name, (a, b) in defined.items():
            for m in re.finditer(r"\b" + re.escape(name) + r"\s*\(", src):
                if a < m.start() < b:
                    continue
                if src[max(0, m.start() - 10):m.start()].rstrip().endswith("function"):
                    continue
                if any(x < m.start() < y for x, y in tops):
                    line = src[:m.start()].count("\n") + 1
                    pytest.fail(f"{path.name}:{line} קורא ל-{name} מחוץ לבלוק שמגדיר אותו")


# ─── הגילוי: אי אפשר להשתמש במה שלא רואים ───────────────────────────────────

def _css():
    return (_ROOT / "frontend/static/css/style.css").read_text(encoding="utf-8")


def test_the_budget_control_is_visible_without_manage_mode():
    """הוא היה מוסתר מאחורי אותו מתג שמסתיר עריכה, מחיקה וסידור. לגביהם
    זה נכון — אלה פעולות על הרשימה. תקציב הוא ההגדרה שבגללה מתקינים
    אפליקציית תקציב, ומתן לא מצא אותה."""
    css = _css()

    assert ".cat-budget-edit { display: none; }" not in css
    assert ".managing .cat-budget-edit" not in css


def test_the_budget_block_gets_its_own_line():
    """הבלוק הוא ‎width: 100%‎ בתוך שורת flex. בלי ‎flex-wrap‎ הוא נדחס
    לצד שם הקטגוריה במקום לרדת מתחתיו."""
    css = _css()
    row = css[css.index(".category-row {"):]
    row = row[:row.index("}")]

    assert "flex-wrap: wrap" in row


def test_manage_mode_still_hides_the_list_management_controls():
    """בקרת-נגד: רק התקציב יצא מ"מצב ניהול". עריכה, מחיקה וסידור
    נשארים מאחוריו — הם כן פעולות על הרשימה."""
    css = _css()

    for control in (".edit-cat-btn", ".delete-cat-btn", ".cat-reorder-btns"):
        assert f"#categoriesArea:not(.managing) {control}" in css


# ─── המבנה שמתן ביקש ────────────────────────────────────────────────────────

def _budget_block():
    """הבלוק של עריכת התקציב בתבנית.

    לא חותכים ב-‎{% endif %}‎ הראשון: יש ‎{% if limit %}checked{% endif %}‎
    בתוך התיבה עצמה, והחיתוך התרחש לפניה. תוחמים לפי סגירת ה-div."""
    html = (_ROOT / "frontend/templates/settings.html").read_text(encoding="utf-8")
    start = html.index('<div class="cat-budget-edit">')
    depth, i = 0, start
    while True:
        if html.startswith("<div", i):
            depth += 1
        elif html.startswith("</div>", i):
            depth -= 1
            if depth == 0:
                return html[start:i + 6]
        i += 1


def test_there_is_exactly_one_toggle_and_it_says_what_it_does():
    """מתג אחד, "קביעת תקציב חודשי". לא שניים, ולא ניסוח שמשאיר את
    המשתמש לנחש מה יקרה."""
    block = _budget_block()

    assert block.count('type="checkbox"') == 1
    assert "קביעת תקציב חודשי" in block


def test_it_is_a_switch_and_not_a_tick_box():
    """מתג הדלקה/כיבוי, כמו כל שאר ההגדרות באפליקציה — ולא תיבת וי.
    ‎pref-switch‎ הוא הרכיב הקיים; בנייה של עוד אחד הייתה מייצרת שני
    מתגים שנראים אחרת באותו מסך."""
    block = _budget_block()

    assert 'class="pref-switch"' in block
    assert 'class="pref-slider"' in block


def test_the_switch_reuses_the_existing_component():
    """בקרת-נגד: הסגנון מגיע מהרכיב המשותף, לא מהעתקה מקומית."""
    css = _css()

    assert ".pref-switch input:checked + .pref-slider" in css
    assert ".cat-budget-toggle" not in css, "נשאר רכיב מקומי מיותר"


def test_turning_it_on_reveals_an_amount_box_and_a_save_button():
    block  = _budget_block()
    fields = block[block.index('class="cat-budget-fields"'):]

    assert 'class="form-input budget-amount"' in fields
    assert "budget-save" in fields and ">שמור<" in fields
    # מוסתר עד שמדליקים
    assert "{% if not limit %}hidden{% endif %}" in block


def test_the_amount_box_is_hidden_until_the_toggle_is_on():
    """‎display: flex‎ של המחבר מנצח את ‎[hidden]‎ של הדפדפן. כל עוד הבלוק
    כולו היה מוסתר מחוץ ל"מצב ניהול" זה לא הורגש — וברגע שהוא נחשף,
    תיבת הסכום וכפתור השמירה הופיעו לכל מי שלא הדליק כלום.

    אותה מלכודת בדיוק כמו בפס "אין חיבור", שבו כבר נכתב ‎[hidden]‎ מפורש."""
    css = _css()

    assert ".cat-budget-fields[hidden] { display: none; }" in css
    assert css.index(".cat-budget-fields {") < css.index(".cat-budget-fields[hidden]"), \
        "הכלל המפורש חייב לבוא אחרי, אחרת הוא לא גובר"
