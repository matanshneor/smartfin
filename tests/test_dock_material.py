"""סרגל הניווט התחתון — חומר שקוף-למחצה עם טשטוש (מתן, 7.10 — עיצוב בנוסח אפל, סעיף 5).

ב-0.97 בלי טשטוש התוכן שמאחור הבליח חד בין התוויות ("+₪14,500" מאחורי
"בית"). מי שביקש בטלפון פחות שקיפות או ניגודיות גבוהה — מקבל סרגל אטום.
בדפדפן: נבדק עם ‎Emulation.setEmulatedMedia‎ (‎prefers-reduced-transparency‎,
‎prefers-contrast‎) שה-‎backdrop-filter‎ המחושב יורד ל-‎none‎ והרקע אטום.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_CSS = (Path(__file__).resolve().parent.parent / "frontend/static/css/style.css").read_text(encoding="utf-8")


def _block(selector, start=0):
    i = _CSS.index(selector + " {", start)
    return _CSS[i:_CSS.index("}", i)]


def test_the_dock_is_frosted_glass():
    nav = _block(".bottom-nav")
    assert "background: var(--dock-bg);" in nav
    # כל שורה לחוד — "backdrop-filter" הוא גם סוף של "-webkit-backdrop-filter"
    assert re.search(r"^\s+backdrop-filter: blur\(", nav, re.M)
    assert re.search(r"^\s+-webkit-backdrop-filter: blur\(", nav, re.M)   # ספארי צריך את הקידומת


@pytest.mark.parametrize("theme", [":root {", ':root[data-theme="dark"] {'])
def test_the_glass_is_see_through_and_has_a_solid_twin(theme):
    i = _CSS.index(theme)
    block = _CSS[i:_CSS.index("}", i)]
    alpha = float(re.search(r"--dock-bg:\s+rgba\([^)]*,\s*([0-9.]+)\)", block).group(1))
    assert 0.5 <= alpha <= 0.85, "אטום מדי — אין טעם בטשטוש; שקוף מדי — התוויות לא נקראות"
    assert re.search(r"--dock-bg-solid:\s+#[0-9A-Fa-f]{6};", block)


def test_less_transparency_or_more_contrast_gets_a_solid_dock():
    q = _CSS.index("@media (prefers-reduced-transparency: reduce), (prefers-contrast: more) {")
    nav = _block(".bottom-nav", q)
    assert "background: var(--dock-bg-solid);" in nav
    assert re.search(r"^\s+backdrop-filter: none;", nav, re.M)
    assert re.search(r"^\s+-webkit-backdrop-filter: none;", nav, re.M)
