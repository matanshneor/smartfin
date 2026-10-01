"""ניסוח אחיד (סבב 4, ה3).

- "1 חברים" → "חבר אחד": ‎count_of‎ בשרת ו-‎sfCount‎ בדפדפן, באותו כלל.
- פנייה ברבים, כמו רוב האפליקציה: "נסו שוב" ולא "נסה שוב". כשאור קיבלה
  "נסה שוב" זה צרם — והמחצית מההודעות פנתה כך.
"""
import glob
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.wording import count_of

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_CASES = [0, 1, 2, 11, "1", "abc", None]


@pytest.mark.parametrize("n,expected", [(1, "חבר אחד"), (2, "2 חברים"), (0, "0 חברים"),
                                         ("1", "חבר אחד"), (None, "0 חברים")])
def test_the_rule(n, expected):
    assert count_of(n, "חבר אחד", "חברים") == expected


def test_the_browser_counts_exactly_like_the_server():
    node = shutil.which("node")
    if not node:
        pytest.skip("node לא מותקן")
    script = (
        "const g = globalThis; g.window = g;"
        "eval(require('fs').readFileSync(process.argv[1], 'utf8')"
        ".match(/window\\.sfCount = function[\\s\\S]*?\\n\\};/)[0]);"
        "console.log(JSON.stringify(JSON.parse(process.argv[2]).map(n => g.sfCount(n, 'חבר אחד', 'חברים'))));"
    )
    out = subprocess.run([node, "-e", script, str(_ROOT / "frontend/static/js/core.js"), json.dumps(_CASES)],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [count_of(n, "חבר אחד", "חברים") for n in _CASES]


def _visible_strings():
    """טקסט שמשתמש רואה: בלי הערות, ובקוד — רק מחרוזות."""
    for f in glob.glob(str(_ROOT / "frontend/templates/*.html")) + \
             glob.glob(str(_ROOT / "frontend/static/js/*.js")) + \
             [str(_ROOT / "backend/app.py"), str(_ROOT / "backend/supabase_config.py")]:
        src = re.sub(r"\{#.*?#\}|<!--.*?-->|/\*.*?\*/|\"\"\".*?\"\"\"", "", open(f, encoding="utf-8").read(), flags=re.S)
        for line in src.split("\n"):
            if line.strip().startswith(("#", "//")):
                continue
            yield Path(f).name, line


@pytest.mark.parametrize("masculine", ["נסה שוב", "הזן ידנית", "בדוק גם", "רק אתה", "תמיד תוכל", 'aria-label="בחר '])
def test_messages_address_the_family_not_one_man(masculine):
    # מילה שלמה: "לבדוק גם" (שם פועל, ניטרלי) מכיל את "בדוק גם"
    pattern = re.compile(r"(?<![א-ת])" + re.escape(masculine))
    hits = [name for name, line in _visible_strings() if pattern.search(line)]
    assert not hits, hits


@pytest.mark.parametrize("template,phrase", [
    ("settings.html", "}} חברים"), ("settings.html", "}} פרויקטים"),
    ("settings.html", "}} עסקאות חוזרות"), ("month.html", "}} קטגוריות ללא"),
    ("project_edit.html", "}} עסקאות"), ("settings.html", "}} ימים"),
])
def test_no_bare_number_before_a_plural(template, phrase):
    """"{{ n }} חברים" הוא "1 חברים" כש-n=1."""
    html = (_ROOT / "frontend/templates" / template).read_text(encoding="utf-8")
    assert phrase not in re.sub(r"\{#.*?#\}", "", html, flags=re.S)


def test_one_name_for_savings_and_for_shared():
    strings = list(_visible_strings())
    assert not [n for n, l in strings if "חסכונות" in l]
    assert not [n for n, l in strings if re.search(r"['\"]משותף['\"]", l)]


# ─── חצים ב-RTL: קדימה ←, אחורה → ────────────────────────────────────────────

@pytest.mark.parametrize("page", ["privacy.html", "terms.html"])
def test_back_points_right(page):
    html = (_ROOT / "frontend/templates" / page).read_text(encoding="utf-8")
    assert ">→ חזרה<" in html and "← חזרה" not in html


def test_a_sequence_of_steps_reads_right_to_left():
    html = (_ROOT / "frontend/templates/project_detail.html").read_text(encoding="utf-8")
    assert '"שייך לפרויקט" ←' in html


@pytest.mark.parametrize("is_future,arrow", [(False, "חזרה לחודש הנוכחי ←"),
                                              (True, "→ חזרה לחודש הנוכחי")],
                         ids=["from-the-past", "from-the-future"])
def test_back_to_this_month_points_the_right_way(is_future, arrow):
    """מנובמבר, כשספטמבר הוא החודש הנוכחי, החזרה היא אחורה בזמן."""
    from jinja2 import Environment
    src = (_ROOT / "frontend/templates/month.html").read_text(encoding="utf-8")
    line = src[src.index("{% if is_current %}"):]
    line = line[:line.index("</p>")]
    html = Environment().from_string(line).render(is_current=False, is_future=is_future,
                                                  url_for=lambda *a, **k: "/month")
    assert arrow in html


def test_the_route_knows_a_future_month():
    import inspect
    from backend import app as app_module
    src = inspect.getsource(app_module.month_view)
    assert "is_future = (year, month) > (now.year, now.month)" in src
    assert src.count("is_future=is_future") == 2


def test_fixed_costs_use_the_same_words_as_the_rest_of_the_app():
    """מתן (30.9): בעסקאות הקבועות "הוצאות/חיסכון" ולא "יוצא/מופרש"."""
    html = (_ROOT / "frontend/templates/month.html").read_text(encoding="utf-8")
    labels = re.findall(r'class="fixed-label">([^<]+)<', html)
    assert labels == ["הוצאות", "הכנסות", "חיסכון"], labels


@pytest.mark.parametrize("totals,expected", [
    ({"קרן": 5000, "גמל": 3000}, {"קרן": 63, "גמל": 37}),          # 62.5 + 37.5 — לא 63 + 38
    ({"א": 1, "ב": 1, "ג": 1}, {"א": 34, "ב": 33, "ג": 33}),
    ({"א": 100}, {"א": 100}),
    ({"א": 0, "ב": 50}, {"ב": 100}),
    ({}, {}),
])
def test_shares_always_add_up_to_a_hundred(totals, expected):
    from backend.wording import share_map
    got = share_map([{"name": n, "total": t} for n, t in totals.items()])
    assert got == expected
    assert not got or sum(got.values()) == 100


def test_the_app_says_monthly_balance_and_never_checking_account():
    """מתן (30.9): "מאזן חודשי" במקום "נשאר בעו״ש" — "שבכלל לא יהיה נשאר בעוש
    באפליקציה". בכל צורת כתיבה, בכל טקסט שמשתמש רואה."""
    forms = re.compile(r'עו״ש|עו\\?"ש|עו&quot;ש|(?<![א-ת])עוש(?![א-ת])')
    hits = [name for name, line in _visible_strings() if forms.search(line)]
    assert not hits, hits
    for page in ("index.html", "month.html", "landing.html"):
        html = re.sub(r"\{#.*?#\}", "", (_ROOT / "frontend/templates" / page).read_text(encoding="utf-8"), flags=re.S)
        # "מאזן החודש" (מתן, 1.10), ולא עוד "מאזן חודשי"
        assert "מאזן החודש" in html and "מאזן חודשי" not in html, page


def test_recurring_transactions_have_one_name():
    """מתן (1.10): "עסקאות קבועות" בכל האפליקציה — לא "עסקה חוזרת" ולא
    "סדרה". בכל טקסט שמשתמש רואה."""
    forms = re.compile(r"עסקה חוזרת|עסקאות חוזרות|העסקה הזאת חוזרת|העסקה חוזרת|סדרה|הסדרה|סדרות")
    hits = [(name, line) for name, line in _visible_strings() if forms.search(line)]
    assert not hits, hits
