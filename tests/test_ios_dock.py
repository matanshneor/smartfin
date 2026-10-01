"""התפריט התחתון נשאר למטה באפליקציה המותקנת באייפון (מתן, 1.10).

באג של iOS: ‎position: fixed‎ נסחף בגלילה ונתקע באמצע המסך. אי אפשר
לשחזר ב-Chromium — כאן נבדקים החשבון והחיווט; את התוצאה בודקים בטלפון.
"""
import json
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_JS = (_ROOT / "frontend/static/js/pwa.js").read_text(encoding="utf-8")


def _run(standalone, cases):
    harness = """
    const listeners = {};
    global.window = { navigator: { standalone: %s }, matchMedia: () => ({ matches: false }),
                      addEventListener() {}, visualViewport: { addEventListener() {} } };
    global.navigator = window.navigator;
    global.document = { addEventListener() {}, createElement: () => ({ style: {}, setAttribute() {}, classList: {} }),
                        body: { appendChild() {} }, querySelectorAll: () => [] };
    global.localStorage = { getItem: () => '1' };
    eval(require('fs').readFileSync(process.argv[1], 'utf8'));
    const f = window.sfDockOffset;
    console.log(JSON.stringify(f ? JSON.parse(process.argv[2]).map(c => f(...c)) : null));
    """ % ("true" if standalone else "false")
    out = subprocess.run(["node", "-e", harness, str(_ROOT / "frontend/static/js/pwa.js"), json.dumps(cases)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_the_menu_moves_to_where_the_visible_screen_ends():
    # מסך מחושב 812, נראה 874 → 62 למטה; מחושב ארוך מהנראה → למעלה; זהים → כלום
    assert _run(True, [[812, 874, 0], [874, 812, 0], [844, 844, 0], [844, 843, 0]]) == [62, -62, 0, 0]


def test_only_in_the_installed_iphone_app():
    assert _run(False, [[812, 874, 0]]) is None


def test_it_runs_when_scrolling_stops_and_not_while_typing():
    part = _JS[_JS.index("window.sfDockOffset"):]
    assert "window.addEventListener('scroll', soon, { passive: true });" in part
    assert "(vv && !typing())" in part
    assert "document.querySelectorAll('.bottom-nav, .fab')" in part
    assert "el.style.translate" in part and "el.style.transform" not in part
