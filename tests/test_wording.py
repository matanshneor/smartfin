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
