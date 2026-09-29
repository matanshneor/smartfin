"""אגורות מוצגות כשיש אגורות — בשרת ובדפדפן, באותו כלל בדיוק.

עד 30.9.2026 כל תבנית עיגלה לשקל, והקלט קיבל אגורות: קפה ב-12.50 הוצג
₪13, ושלוש קניות של 10.40 הוצגו ₪10 כל אחת ו-₪31 ביחד. מתן בחר: אגורות
כשיש. הכלל חי בשני מקומות — ‎format_money‎ (תבניות, התראות) ו-‎sfMoney‎
(אנימציות, מקרא, גרפים) — והבדיקה כאן היא מה שמונע מהם להיפרד.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.money import format_money
from tests.test_project_only_month import month_page, _row  # noqa: F401 (fixture)

pytestmark = pytest.mark.unit

_CORE = Path(__file__).resolve().parent.parent / "frontend/static/js/core.js"

_CASES = [12.5, 180, 180.0, 1234.4, 1234567.89, 0, 0.1 + 0.2, 10.40 * 3,
          99.999, 99.994, 0.005, 5000.10, -300, -12.5]


@pytest.mark.parametrize("value,expected", [
    (12.5, "12.50"), (180, "180"), (1234.4, "1,234.40"), (0.1 + 0.2, "0.30"),
    (10.40 * 3, "31.20"), (99.999, "100"), (None, "0"), ("abc", "0"),
])
def test_the_rule(value, expected):
    assert format_money(value) == expected


def test_the_browser_says_exactly_what_the_server_says():
    node = shutil.which("node")
    if not node:
        pytest.skip("node לא מותקן")
    script = (
        "const g = globalThis; g.window = g;"
        "eval(require('fs').readFileSync(process.argv[1], 'utf8')"
        ".match(/window\\.sfMoney = function[\\s\\S]*?\\n\\};/)[0]);"
        "console.log(JSON.stringify(JSON.parse(process.argv[2]).map(v => g.sfMoney(v))));"
    )
    out = subprocess.run([node, "-e", script, str(_CORE), json.dumps(_CASES)],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr

    browser = json.loads(out.stdout)
    server = [format_money(v) for v in _CASES]
    assert browser == server, list(zip(_CASES, server, browser))


def test_the_month_page_shows_agorot_and_totals_add_up(month_page):
    """שלוש קניות של 10.40: כל אחת ₪10.40, והקטגוריה ₪31.20 — לא 10/10/10 ו-31."""
    rows = [{**_row(f"קנייה{n}", project=False), "id": f"k{n}", "amount": 10.40} for n in range(3)]

    html = month_page(rows)

    assert html.count("₪10.40") >= 3
    assert "₪31.20" in html
    assert "₪31<" not in html and "₪10<" not in html
