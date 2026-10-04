""""כל העסקאות" בעמוד החודש (מתן, 5.10).

האחרונות מופיעות מיד, והרשימה המלאה — עם החיפוש והסינון — במסך משלה.
עד אז הכל היה שורת "הצגת הכל" אחת שנפתחה במקום.
"""
from pathlib import Path

import pytest

from tests.test_empty_states import _TX, _render_month

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent


def _txs(n):
    return [dict(_TX, id=f"t{i}", description=f"עסקה {i}", date=f"2026-09-{28 - i:02d}") for i in range(n)]


def _section(html):
    part = html[html.index('id="allTx"'):]
    return part[:part.index("<!-- פרויקטים החודש")] if "<!-- פרויקטים החודש" in part else part


def test_the_latest_five_show_right_away():
    section = _section(_render_month(_txs(12)))
    preview = section[section.index('class="cat-tx-list cat-tx-list-standalone tx-preview"'):]
    preview = preview[:preview.index("</ul>")]

    assert preview.count('class="cat-tx-row"') == 5
    assert "עסקה 0" in preview and "עסקה 4" in preview and "עסקה 5" not in preview


def test_the_rest_with_search_and_filters_is_on_its_own_screen():
    section = _section(_render_month(_txs(12)))
    screen = section[section.index('id="txScreen"'):]

    assert 'id="txScreenOpen"' in section and "לכל עסקאות החודש" in section
    assert 'role="dialog"' in section[section.index('id="txScreen"') - 60:section.index('id="txScreen"') + 120]
    assert screen.count('class="cat-tx-row"') == 12
    assert 'id="txSearch"' in screen and 'id="txScreenClose"' in screen
    # החיפוש רק במסך — לא בתצוגה המקדימה
    assert section.index('id="txSearch"') > section.index('id="txScreen"')


def test_five_or_fewer_need_no_second_screen():
    section = _section(_render_month(_txs(5)))

    assert section.count('class="cat-tx-row"') == 5
    assert 'id="txScreen"' not in section and 'id="txScreenOpen"' not in section


def test_the_search_filters_the_screen_and_survives_an_edit():
    js = (_ROOT / "frontend/static/js/month.js").read_text(encoding="utf-8")

    assert "document.querySelectorAll('#txScreen .tx-screen-list .cat-tx-row')" in js
    # כפתור החזרה של הטלפון סוגר את המסך, ורענון אחרי עריכה פותח אותו שוב
    assert "history.pushState({ sfTxScreen: true }, '', '#all-tx')" in js
    assert "window.addEventListener('sf:refreshed'" in js and "restoreTxState();" in js


def test_the_search_also_knows_the_category_name():
    """"סופר" מוצא את "רמי לוי" שבקטגוריה "סופר ומזון" (מתן, 5.10)."""
    tx = dict(_TX, description="רמי לוי", category_name="סופר ומזון", project_name="שיפוץ")
    html = _render_month([tx] * 6)
    screen = html[html.index('id="txScreen"'):]
    assert 'data-search="סופר ומזון שיפוץ"' in screen
    js = (_ROOT / "frontend/static/js/month.js").read_text(encoding="utf-8")
    assert "+ ' ' + (row.dataset.search || '');" in js
