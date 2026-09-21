"""
מדיניות הפרטיות הפנתה לפרטי קשר שלא היו קיימים.

הסעיף אמר "ניתן לפנות דרך פרטי הקשר המופיעים באפליקציה", ובאפליקציה
לא היה שום ‎mailto‎, שום "צור קשר", שום כתובת. זו הבטחה במסגרת GDPR —
באותו סעיף שמפרט זכות עיון ומחיקה — בלי מנגנון מאחוריה. וזה גם הערוץ
היחיד שמשתמש תקוע היה מחפש.

העמודים המשפטיים פתוחים לכל האינטרנט ומסומנים לאינדוקס, ולכן הכתובת
שם מורכבת בדפדפן: טקסט אמיתי ב-DOM לקוראי מסך ולהעתקה, ושום דבר
לסורק שלא מריץ JavaScript. בהגדרות, מאחורי התחברות, היא גלויה כרגיל.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_TPL  = _ROOT / "frontend/templates"

_ADDRESS = "matanshneor1@gmail.com"
_USER, _DOMAIN = _ADDRESS.split("@")


def _read(name):
    return (_TPL / name).read_text(encoding="utf-8")


# ─── ההבטחה מקוימת ──────────────────────────────────────────────────────────

def test_the_privacy_policy_no_longer_points_at_nothing():
    privacy = _read("privacy.html")

    assert "פרטי הקשר\n        המופיעים באפליקציה" not in privacy
    assert 'data-contact' in privacy


@pytest.mark.parametrize("page", ["privacy.html", "terms.html"])
def test_both_legal_pages_have_a_way_to_make_contact(page):
    html = _read(page)

    assert "יצירת קשר" in html
    assert f'data-user="{_USER}"' in html
    assert f'data-domain="{_DOMAIN}"' in html


def test_a_signed_in_user_finds_it_where_things_break():
    """מי שמשהו לא עובד אצלו נמצא באפליקציה, לא בעמוד המשפטי."""
    settings = _read("settings.html")

    assert f"mailto:{_ADDRESS}" in settings
    assert "יצירת קשר" in settings


# ─── לא לחשוף לבוטים בעמודים הפתוחים ────────────────────────────────────────

@pytest.mark.parametrize("page", ["privacy.html", "terms.html"])
def test_the_public_pages_never_spell_the_address_out(page):
    """עמוד ציבורי שמסומן לאינדוקס הוא בדיוק מה שקוצרים. סורק מחפש
    ‎mailto:‎ ומחרוזת עם ‎@‎ — ואין שם לא זה ולא זה."""
    html = _read(page)

    assert _ADDRESS not in html, "הכתובת כתובה במלואה"
    assert "mailto:" not in html


@pytest.mark.parametrize("page", ["privacy.html", "terms.html"])
def test_there_is_still_a_way_without_javascript(page):
    """בלי JavaScript אין קישור — וחייבת להישאר דרך ליצור קשר."""
    html = _read(page)
    block = html[html.index("data-contact"):]
    block = block[:block.index("</span>")]

    assert "<noscript>" in block
    assert _USER in block and "gmail" in block


@pytest.mark.parametrize("page", ["privacy.html", "terms.html"])
def test_the_page_actually_loads_the_script(page):
    assert "js/contact.js" in _read(page)


# ─── מה שנגיש לבני אדם נשאר נגיש ────────────────────────────────────────────

def test_the_assembled_address_is_real_text_not_a_picture():
    """קורא מסך צריך להקריא אותה, ומשתמש צריך לסמן ולהעתיק."""
    js = (_ROOT / "frontend/static/js/contact.js").read_text(encoding="utf-8")

    assert "link.textContent = address" in js
    assert "link.href = 'mailto:' + address" in js


def test_the_noscript_fallback_hides_its_punctuation_from_screen_readers():
    """‎[at]‎ ו-‎[dot]‎ נועדו לעין, לא לאוזן — קורא מסך שמקריא אותם
    הופך כתובת פשוטה לחידה."""
    privacy = _read("privacy.html")
    block = privacy[privacy.index("<noscript>"):]
    block = block[:block.index("</noscript>")]

    assert block.count('aria-hidden="true"') == 2
