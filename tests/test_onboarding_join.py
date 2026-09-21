"""
הצטרפות למשפחה שעוד לא סיימה את ההגדרה פיצלה אותה לשתיים.

האשף הציג את קוד ההזמנה בשלב 2 — לפני שנוצרו הקטגוריות — ומי שקיבל
אותו והצטרף מיד נחת בעצמו על האשף, כי "צריך הגדרה" נמדד לפי היעדר
קטגוריות. בלי שום הודעה, ועל מסך הפתיחה "משפחה חדשה או הצטרפות?".

זה נראה בדיוק ככישלון, והמוצא המתבקש הוא הכפתור שמוצע — "פותחים
משפחה חדשה". שניים במשפחות נפרדות, כל אחד עם קוד משלו, ואף אחד לא
מבין למה השני לא רואה את העסקאות.

שני תיקונים: הקוד לא מוצג לפני שיש למה להזמין, ומי שכבר נחת שם מקבל
הסבר במקום מסך פתיחה.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from backend import app as app_module
from backend.app import app

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_HTML = (_ROOT / "frontend/templates/onboarding.html").read_text(encoding="utf-8")
_JS   = (_ROOT / "frontend/static/js/onboarding.js").read_text(encoding="utf-8")

_FAM = "11111111-1111-1111-1111-111111111111"
_ME  = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setattr(app_module.db, "family_needs_onboarding", lambda fid: True)
    monkeypatch.setattr(app_module.db, "get_family",
                        lambda fid: {"id": _FAM, "name": "שניאור", "invite_code": "K4F2QX",
                                     "manager_id": "someone-else"})
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = _ME; sess["family_id"] = _FAM; sess["user_name"] = "מתן"
        yield c


# ─── המניעה: אין הזמנה לפני שיש למה להזמין ──────────────────────────────────

def test_the_invite_code_is_not_a_step_in_the_middle_any_more():
    """הקוד הוצג בשלב 2 מתוך 4 — כלומר לפני שהמשפחה בכלל קיימת
    מבחינת האפליקציה."""
    assert 'id="stepInvite"' in _HTML
    assert 'id="step2"' in _HTML and 'id="step4"' not in _HTML


def _success_handler(marker):
    """גוף ה-‎.then(function (…) { … })‎ שאחרי ‎marker‎, לפי איזון סוגריים.

    סימן טקסטואלי לסוף הבלוק (‎"}).catch"‎) נשבר בכל שינוי עיצוב, והבדיקה
    אז בולעת את שאר הקובץ ומדווחת ירוק על כלום. הספירה לא נשברת."""
    body = _JS[_JS.index(marker):]
    head = re.search(r"\.then\(function \([A-Za-z_$][\w$]*\) \{", body)
    assert head, f"לא נמצא מטפל הצלחה אחרי {marker}"

    start = head.end()
    depth = 1
    for i in range(start, len(body)):
        if body[i] == "{":
            depth += 1
        elif body[i] == "}":
            depth -= 1
            if depth == 0:
                return body[start:i]
    raise AssertionError("הסוגריים לא נסגרו")


def test_the_invite_screen_comes_after_the_wizard_finishes():
    """הוא מוצג רק בתשובה מוצלחת של ‎/api/onboarding/complete‎."""
    block = _success_handler("onboarding/complete")

    assert "stepInvite.style.display = 'block'" in block
    assert "window.location.href = '/'" not in block, "עדיין מדלג ישר לאפליקציה"


def test_a_joiner_goes_straight_into_the_app():
    """מי שמצטרף למשפחה מוגדרת לא צריך מסך הזמנה — הוא לא הזמין אף אחד,
    והמשפחה כבר קיימת. הוא נכנס."""
    block = _success_handler("family/join")

    assert "window.location.href = '/'" in block
    assert "stepInvite" not in block, "המצטרף מקבל את מסך ההזמנה במקום להיכנס"


def test_the_wizard_is_three_steps_now():
    """ההזמנה ירדה מהרצף, אז גם הנקודות."""
    assert _HTML.count('class="step-dot') == 3
    assert "dotStep4" not in _HTML and "dotStep4" not in _JS


# ─── החילוץ: מי שכבר נחת שם ─────────────────────────────────────────────────

def test_a_joiner_waiting_on_an_unfinished_family_gets_an_explanation(client, monkeypatch):
    """הלב. עד היום הוא ראה את מסך הפתיחה, ולחץ על "משפחה חדשה"."""
    monkeypatch.setattr(app_module.db, "get_family_members",
                        lambda fid: [{"id": _ME, "name": "מתן"},
                                     {"id": "other", "name": "אור"}])

    html = client.get("/onboarding").get_data(as_text=True)

    assert "הצטרפתם בהצלחה" in html
    assert "אור" in html
    assert 'id="step0"' not in html, "מסך הפתיחה עדיין מוצג"


def test_the_manager_keeps_the_wizard_even_after_someone_joins(client, monkeypatch):
    """הסכנה בתיקון עצמו: מי שפתח את המשפחה עדיין באמצע האשף כשחבר
    מצטרף. אם גם הוא יקבל את מסך ההמתנה — שניהם ממתינים זה לזה
    לנצח, ואף אחד לא יכול לסיים את ההגדרה."""
    monkeypatch.setattr(app_module.db, "get_family",
                        lambda fid: {"id": _FAM, "name": "שניאור",
                                     "invite_code": "K4F2QX", "manager_id": _ME})
    monkeypatch.setattr(app_module.db, "get_family_members",
                        lambda fid: [{"id": _ME, "name": "מתן"},
                                     {"id": "other", "name": "אור"}])

    html = client.get("/onboarding").get_data(as_text=True)

    assert 'id="step0"' in html, "מי שפותח את המשפחה ננעל מחוץ לאשף שלו"
    assert "הצטרפתם בהצלחה" not in html


def test_the_first_member_still_gets_the_wizard(client, monkeypatch):
    """בקרת-נגד, והחשובה כאן: מי שפתח את המשפחה חייב לראות את האשף."""
    monkeypatch.setattr(app_module.db, "get_family_members",
                        lambda fid: [{"id": _ME, "name": "מתן"}])

    html = client.get("/onboarding").get_data(as_text=True)

    assert 'id="step0"' in html
    assert "הצטרפתם בהצלחה" not in html


def test_an_unreadable_member_list_falls_back_to_the_wizard(client, monkeypatch):
    """אם אי אפשר לדעת מי עוד במשפחה, האשף הוא ברירת המחדל הבטוחה:
    לחסום את מי שבאמת צריך להגדיר גרוע מלהראות מסך מיותר."""
    def _boom(fid):
        raise app_module.db.DataUnavailable("members")
    monkeypatch.setattr(app_module.db, "get_family_members", _boom)

    assert 'id="step0"' in client.get("/onboarding").get_data(as_text=True)


# ─── הקובץ לא נופל על המסך החדש ─────────────────────────────────────────────

_HARNESS = r"""
const fs = require('fs');
const present = new Set(JSON.parse(process.argv[3]));
const bound = [];

function el(id) {
    return {
        id,
        style: {},
        classList: { toggle() {}, add() {}, remove() {} },
        addEventListener: (type) => bound.push(id + ':' + type),
        appendChild() {}, querySelectorAll: () => [], focus() {},
        value: '', textContent: '', checked: false, innerHTML: '',
    };
}

const g = globalThis;
g.document = {
    getElementById:   (id) => (present.has(id) ? el(id) : null),
    querySelectorAll: () => [],
    querySelector:    () => null,
    addEventListener() {},
    createElement:    () => el('new'),
};
g.window = g;
g.navigator = { clipboard: { writeText: () => Promise.resolve() } };
g.location = { href: '/onboarding' };
g.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
g.sfNetError = () => '';

(0, eval)(fs.readFileSync(process.argv[2], 'utf8'));
console.log(JSON.stringify({ bound }));
"""


def _run(ids):
    """מריצה את ‎onboarding.js‎ האמיתי מול DOM שמכיל רק את ה-ids שנמסרו."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node לא מותקן")
    harness = _ROOT / "tests" / "_onboarding_harness.js"
    harness.write_text(_HARNESS, encoding="utf-8")
    try:
        out = subprocess.run(
            [node, str(harness),
             str(_ROOT / "frontend/static/js/onboarding.js"), json.dumps(ids)],
            capture_output=True, text=True, timeout=30,
        )
    finally:
        harness.unlink(missing_ok=True)
    return out


_WIZARD_IDS = re.findall(r'id="([A-Za-z][\w-]*)"', _HTML)


def test_the_script_survives_a_page_that_has_no_wizard_on_it():
    """הלב של הפריט הזה מבחינת JS. מסך ההמתנה מוגש במקום האשף כולו,
    ואין בו אף אחד מהאלמנטים. בלי היציאה המוקדמת הקובץ נופל על
    הראשון שחסר — בדיוק כמו ש-core.js נפל על ‎sessionStorage‎."""
    out = _run(["stepWaiting"])

    assert out.returncode == 0, f"הקובץ קרס על מסך ההמתנה:\n{out.stderr[:800]}"
    assert json.loads(out.stdout)["bound"] == [], "נקשרו מאזינים לאלמנטים שלא קיימים"


def test_the_wizard_itself_still_wires_everything_up():
    """בקרת-נגד: היציאה המוקדמת לא מכבה את האשף האמיתי."""
    out = _run(_WIZARD_IDS)

    assert out.returncode == 0, f"הקובץ קרס על האשף:\n{out.stderr[:800]}"
    bound = json.loads(out.stdout)["bound"]
    for expected in ("chooseCreateBtn:click", "toStep2Btn:click",
                     "finishOnboardingBtn:click", "finishBtn:click"):
        assert expected in bound, f"{expected} לא נקשר (נקשרו: {bound})"
