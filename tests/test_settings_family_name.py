"""הגדרות: שם המשפחה בצד שמאל של ראש העמוד (מתן, 1.10 — אפשרות ה)."""
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent


def test_the_family_name_sits_on_the_left_of_the_title():
    html = (_ROOT / "frontend/templates/settings.html").read_text(encoding="utf-8")
    top = html[html.index('<div class="hero-top settings-hero-top">'):html.index('<div class="hero-profile">')]
    assert top.index('<h1 class="hero-title">הגדרות</h1>') < top.index('<p class="settings-family-name">')
    assert "hero-subtitle" not in top
    css = (_ROOT / "frontend/static/css/style.css").read_text(encoding="utf-8")
    rule = css[css.index(".settings-family-name {"):]
    rule = rule[:rule.index("}")]
    assert "text-align: left;" in rule and "font-size: 1.1rem;" in rule and "min-width: 0;" in rule


def test_renaming_updates_the_name_at_the_top():
    js = (_ROOT / "frontend/static/js/settings.js").read_text(encoding="utf-8")
    assert "document.querySelectorAll('.settings-family-name').forEach(el => { el.textContent = newName; });" in js
