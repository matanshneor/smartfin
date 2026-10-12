"""ה-+ ליד הסרגל, ולשוניות שלא נכנסות להיסטוריה (מתן, 11.10).

ה-+ צף מעל התוכן, ובנקודת גלילה מסוימת ישב בדיוק מתחת ל"לכל החודש" ונראה
שייך לו. עכשיו הוא עיגול זהב משמאל לסרגל, באותה שורה.

"כשאני גולל את כל העמוד, הוא מעביר לי בין עמודים": באייפון החלקה מהקצה היא
"אחורה" של המערכת, וכל לחיצה על הסרגל הוסיפה עמוד להיסטוריה. עכשיו הלשוניות
מחליפות זו את זו. בדפדפן: אחרי 5 לחיצות על הסרגל ההיסטוריה לא גדלה, ומעבר
חודש חלק ממשיך לעבוד.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_CSS = (_ROOT / "frontend/static/css/style.css").read_text(encoding="utf-8")
_CORE = (_ROOT / "frontend/static/js/core.js").read_text(encoding="utf-8")


def _rule(selector):
    body = _CSS[_CSS.index(selector + " {"):]
    return body[:body.index("}")]


def test_the_plus_is_a_gold_circle_beside_the_bar():
    fab = _rule(".fab")
    assert "border-radius: 50%;" in fab
    assert "width: var(--fab-size);" in fab
    assert "(var(--dock-height) - var(--fab-size)) / 2" in fab      # באמצע גובה הסרגל
    nav = _rule(".bottom-nav")
    assert "left: calc(var(--dock-side) + var(--fab-size) + 14px);" in nav


def test_pages_without_a_plus_get_the_whole_bar():
    assert "body.no-fab .bottom-nav { left: var(--dock-side); }" in _CSS


def test_the_page_no_longer_keeps_room_for_a_floating_plus():
    assert "96px" not in _rule(".main-content")


def test_switching_tabs_does_not_add_to_history():
    block = _CORE[_CORE.index("const TABS = ['/', '/month', '/months', '/projects', '/settings'];"):]
    block = block[:block.index("})();")]
    assert "location.replace(url.href);" in block
    assert "window.addEventListener('click'" in block          # אחרי month.js
    assert "if (e.defaultPrevented" in block


def test_android_sideways_back_is_off():
    assert "overscroll-behavior-x: none;" in _rule("html")
