""""מאזן חודשי" (לשעבר "נשאר בעו״ש") בעמוד החודש — בלי אדום כשעוד אין הכנסות, ובלי "-₪0".

דף הבית כבר ידע: חודש בלי הכנסה אינו גירעון, כי עוד אין ממה להחסיר.
עמוד החודש, באותו מצב בדיוק, הציג "₪-800" באדום. ובלי JS (או לפני שאנימציית
הספירה רצה) המינוס עמד אחרי ה-₪.
"""
import re

import pytest

from tests.test_project_only_month import month_page, _row  # noqa: F401 (fixture)

pytestmark = pytest.mark.unit


def _chip(html):
    """המלבן של המאזן, מהתגית הפותחת (עליה יושב סימון הגירעון) ועד הסכום."""
    i = html.rindex('<div class="month-net', 0, html.index("מאזן החודש"))
    return html[i:html.index("</p>", html.index("month-net-value", i)) + 4]


def _expense(amount, kind="expense"):
    row = _row(f"{kind}-{amount}", project=False)
    return {**row, "id": f"{kind}-{amount}", "amount": float(amount), "type": kind}


def test_spending_before_any_income_is_not_a_deficit(month_page):
    chip = _chip(month_page([_expense(800)]))

    assert "deficit" not in chip, "גירעון אדום לפני שנכנסה הכנסה"
    assert "-" not in re.sub(r"<[^>]+>", "", chip).replace("מאזן החודש", "")


def test_a_real_deficit_is_red_with_the_minus_before_the_shekel(month_page):
    """בקרת-נגד, ובאותה נגיעה: ‎-₪300‎ ולא ‎₪-300‎."""
    chip = _chip(month_page([_expense(500, "income"), _expense(800)]))

    assert "deficit" in chip
    assert "-₪300" in re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", chip))


def test_forty_agorot_short_is_not_minus_zero(month_page):
    chip = _chip(month_page([_expense(500, "income"), _expense(500.40)]))

    assert "deficit" not in chip
