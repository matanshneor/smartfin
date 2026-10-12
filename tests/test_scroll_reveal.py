"""כניסה עם הגלילה (מתן, 11.10): "שמה שנכנס יתחיל להיכנס לאט עם הגלילה".

כרטיס שמתחת למסך נכנס כשגוללים אליו, צמוד למיקום הגלילה — לא אנימציה בזמן
שרצה בטעינה כשאיש לא רואה. בדפדפן (כרום, נתוני דוגמה): השקיפות עולה בהדרגה
עם הגלילה (0.30 → 0.51 → 0.73 → 0.94 → 1), בסוף כל עמוד אין כרטיס דהוי, ובמסלול
החלופי (בלי ‎animation-timeline‎) כרטיס שדילגו מעליו מופיע כשגוללים אליו.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_CSS = (_ROOT / "frontend/static/css/style.css").read_text(encoding="utf-8")
_MOTION = (_ROOT / "frontend/static/js/motion.js").read_text(encoding="utf-8")


def test_cards_below_the_fold_enter_with_the_scroll():
    block = _CSS[_CSS.index("@supports (animation-timeline: view()) {"):]
    block = block[:block.index("}\n}")]
    assert "animation-timeline: view(block);" in block
    assert "animation-range: entry 0% entry 140px;" in block      # אותו מרחק לכל כרטיס


def test_the_reveal_moves_with_translate_not_transform():
    """‎transform‎ דורס את ההחלקות (כרטיס "השבוע" כותב ‎transform‎)."""
    keyframes = _CSS[_CSS.index("@keyframes reveal-in {"):]
    keyframes = keyframes[:keyframes.index("}\n}")]
    assert "translate:" in keyframes and "transform" not in keyframes


def test_only_cards_below_the_fold_wait_for_the_scroll():
    assert "if (!belowTheFold(el)) return;" in _MOTION
    assert "const below = all.filter(belowTheFold);" in _MOTION


def test_older_browsers_get_a_soft_entrance_instead():
    assert "CSS.supports('animation-timeline: view()')" in _MOTION
    assert "new IntersectionObserver(" in _MOTION
    assert ".reveal-fallback.is-in { opacity: 1; translate: 0 0; }" in _CSS


def test_reduced_motion_shows_everything_at_once():
    assert "if (reduceMotion) return;" in _MOTION[_MOTION.index("function setupReveal"):]
    rm = _CSS[_CSS.rindex("@media (prefers-reduced-motion: reduce) {", 0, _CSS.index(".reveal-fallback.is-in")+400):]
    assert ".reveal-scroll { animation: none; }" in rm


def test_new_content_after_a_soft_swap_also_enters_with_the_scroll():
    hook = _MOTION[_MOTION.index("window.addEventListener('sf:refreshed'"):]
    assert "setupReveal(" in hook[:hook.index("});")]
