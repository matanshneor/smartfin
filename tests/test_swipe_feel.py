"""החלקות קלות ונוחות, בזמן אמת (מתן, 11.10).

כל ההחלקות באתר עובדות באותו אופן: מה שנגרר זז עם האצבע אחד לאחד, ההחלטה
בשחרור היא לפי לאן התנועה מכוונת (מרחק + תנופה) ולא לפי מרחק בלבד, והחזרה
או היציאה ממשיכות את מהירות האצבע. בדפדפן: נמדד עם מגע אמיתי (CDP).
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_JS = Path(__file__).resolve().parent.parent / "frontend/static/js"
_CSS = (Path(__file__).resolve().parent.parent / "frontend/static/css/style.css").read_text(encoding="utf-8")


def _read(name):
    return (_JS / name).read_text(encoding="utf-8")


def test_the_week_card_follows_the_finger_one_to_one():
    """עד 11.10 הכרטיס זז בחצי ממהירות האצבע (‎dx * 0.45‎)."""
    core = _read("core.js")
    block = core[core.index("let sx = null, sy = 0, axis = null, drag = null, x = 0, stopSpring = null;"):]
    block = block[:block.index("})();")]
    assert "0.45" not in block
    assert "placeCard(drag, canGo(drag, raw < 0) ? raw : window.sfRubber(raw, drag.offsetWidth));" in block
    assert "window.sfSpring(" in block                      # חזרה בקפיץ, לא מעבר קבוע


def test_the_next_week_is_fetched_while_swiping():
    core = _read("core.js")
    assert "if (canGo(drag, older)) fetchWeek(Number(drag.dataset.offset) + (older ? 1 : -1));" in core


def test_the_month_follows_the_finger_and_decides_by_aim():
    month = _read("month.js")
    block = month[month.index("const SLIDE ="):]
    assert "place(t.clientX - sx);" in block
    assert "const aim = x + window.sfProject(v, 0.99);" in block
    assert "(aim < 0) === (x < 0)" in block                 # התחרטות לא עוברת חודש


def test_a_finished_entrance_animation_lets_go_of_the_card():
    """‎anim-rise‎ עם ‎forwards‎ החזיק את ‎transform‎ — והחלקה לא הזיזה את
    כרטיס "השבוע" עד שהתחלף."""
    motion = _read("motion.js")
    assert "el.classList.remove('anim-rise');" in motion
    assert "e.animationName !== 'rise-in'" in motion


def test_swiping_a_row_does_not_scroll_the_page_under_it():
    tx = _read("transactions.js")
    move = tx[tx.index("drag.deltaX = over <= 0 ? raw"):]
    move = move[:move.index("}, { passive: false });")]
    assert "if (e.cancelable) e.preventDefault();" in move
    assert "document.addEventListener('touchend'" not in move     # אותו מאזין


def test_the_browser_knows_sideways_belongs_to_the_page():
    assert re.search(r"\.transaction-item, \.cat-tx-row, \.recurring-row, \.week-card \{ touch-action: pan-y; \}", _CSS)


# ─── ההגדרות נכנסות במסך אחד; חלון ההוספה נמתח למעלה (מתן, 11.10) ─────────

_SETTINGS = (Path(__file__).resolve().parent.parent / "frontend/templates/settings.html").read_text(encoding="utf-8")


def test_settings_does_not_keep_room_for_a_plus_button_it_does_not_have():
    """96 פיקסלים בתחתית בשביל כפתור + שלא קיים בהגדרות — אחרי החלקה לתחתית
    הקפיץ נעצר שם והכותרת "הגדרות" נשארה מחוץ למסך. בדפדפן: נמדד, הדף לא
    גבוה מהמסך כשהכול סגור (גם עם אזורי האייפון של האפליקציה המותקנת)."""
    assert "{% block body_class %}no-fab settings-page{% endblock %}" in _SETTINGS
    rule = _CSS[_CSS.index("body.settings-page .main-content {"):]
    rule = rule[:rule.index("}")]
    assert "96px" not in rule and "env(safe-area-inset-bottom, 0px)" in rule


def test_the_add_window_stretches_up_and_springs_back():
    tx = _read("transactions.js")
    move = tx[tx.index("overlay.addEventListener('touchmove'"):]
    move = move[:move.index("}, { passive: false });")]
    assert "(dy < 0 && !atEnd)" in move                     # רק כשהתוכן כבר בסופו
    assert "paint(raw >= 0 ? raw : sfRubber(raw, sheet.offsetHeight));" in move
    # ובלי רווח ריק מתחת לחלון כשהוא נמתח
    assert "box-shadow: 0 160px 0 0 var(--color-bg-elevated)" in _CSS
