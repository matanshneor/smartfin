"""מרווח בין אותיות בעברית (מתן, 7.10 — עיצוב בנוסח אפל, סעיף 6).

מרווח רחב שייך לאותיות גדולות באנגלית; בעברית הוא מפרק מילים — "ניהול
תקציב משפחתי" בדף הנחיתה נקרא "נ י ה ו ל". קודי ההזמנה נשארים מרווחים
בכוונה: קוד קל לקרוא ולהקליד כשהתווים לא נוגעים זה בזה.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_CSS = (Path(__file__).resolve().parent.parent / "frontend/static/css/style.css").read_text(encoding="utf-8")


def _tracking(selector):
    i = _CSS.index(selector + " {")
    return float(re.search(r"letter-spacing:\s*(-?[0-9.]+)em", _CSS[i:_CSS.index("}", i)]).group(1))


@pytest.mark.parametrize("selector", [".hero-label", ".lp-eyebrow"])
def test_small_hebrew_labels_are_not_spaced_apart(selector):
    assert _tracking(selector) <= 0.03


def test_the_big_number_is_tightened():
    assert _tracking(".hero-amount") <= -0.02


@pytest.mark.parametrize("selector", [".invite-code-card .invite-code-value", ".invite-code-input"])
def test_invite_codes_stay_spaced(selector):
    assert _tracking(selector) >= 0.1
