"""
בדיקות לפונט המקומי.

Rubik נטען מגוגל, עם שלוש תוצאות: הוא חסם את הרינדור עד שהגיע; גוגל
שומר אותו ליום אחד בלבד, אז משתמש יומי הוריד אותו מחדש כל יום; וה-PWA
נפל לפונט מערכת באופליין, כי ה-Service Worker לא מיירט מקורות חיצוניים.

ובנוסף: כתובת ה-IP של כל משתמש נשלחה לגוגל בכל טעינה, באפליקציה עם
מדיניות פרטיות מפורסמת על כספי משק בית.
"""
import re
from pathlib import Path

import pytest

from backend.app import app

pytestmark = pytest.mark.unit

_ROOT  = Path(__file__).resolve().parent.parent
_FONTS = _ROOT / "frontend/static/fonts"
_CSS   = (_FONTS / "rubik.css").read_text(encoding="utf-8")


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


# ─── שום דבר לא נטען מגוגל ───────────────────────────────────────────────────

@pytest.mark.parametrize("page", [
    p.name for p in (_ROOT / "frontend/templates").glob("*.html")
])
def test_no_template_reaches_out_to_google(page):
    html = (_ROOT / "frontend/templates" / page).read_text(encoding="utf-8")

    assert "fonts.googleapis" not in html, f"{page} עדיין טוען פונט מגוגל"
    assert "fonts.gstatic" not in html


def test_the_policy_no_longer_allows_google_either(client):
    """מדיניות שמתירה מקורות שלא בשימוש היא משטח תקיפה מיותר."""
    csp = client.get("/login").headers["Content-Security-Policy"]

    assert "googleapis" not in csp and "gstatic" not in csp
    assert "font-src 'self'" in csp


# ─── הקבצים באמת שם ──────────────────────────────────────────────────────────

def test_every_font_the_css_asks_for_exists_and_is_a_real_font(client):
    """קישור שבור היה נופל חזרה לפונט מערכת — כלומר בדיוק מה שתיקנו,
    רק בלי שאף אחד ישים לב."""
    urls = re.findall(r"url\('([^']+)'\)", _CSS)

    assert len(urls) == 8, f"{len(urls)} קבצים — צפויים 8 (4 משקלים × 2 תת-קבוצות)"
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, url
        assert response.get_data()[:4] == b"wOF2", f"{url} אינו woff2 תקין"


def test_only_hebrew_and_latin_are_shipped():
    """גוגל מגיש שש תת-קבוצות לכל משקל — קירילית, יוונית, ערבית ועוד.
    אף אחת מהן לא רלוונטית, וכל אחת היא קובץ נוסף."""
    subsets = set(re.findall(r"/static/fonts/rubik-(\w+)-\d+\.woff2", _CSS))

    assert subsets == {"hebrew", "latin"}


def test_the_weights_match_what_the_stylesheet_uses():
    """משקל שלא נטען מזויף על ידי הדפדפן ונראה אחרת; משקל שנטען ולא
    בשימוש הוא הורדה לחינם."""
    app_css = (_ROOT / "frontend/static/css/style.css").read_text(encoding="utf-8")
    used   = set(re.findall(r"font-weight:\s*(\d00)", app_css))
    loaded = set(re.findall(r"font-weight:\s*(\d+)", _CSS))

    assert used <= loaded, f"בשימוש ולא נטענים: {used - loaded}"
    assert loaded - used == set(), f"נטענים ולא בשימוש: {loaded - used}"


def test_text_is_visible_while_the_font_loads():
    """בלי swap, הדפדפן מסתיר טקסט עד שהפונט מגיע — מסך ריק במקום
    טקסט בפונט מערכת."""
    # רק בתוך כללי @font-face — האזכור בהערה שמסבירה את זה לא נספר
    faces = re.findall(r"@font-face\s*\{[^}]*\}", _CSS)

    assert len(faces) == 8
    assert all("font-display: swap" in f for f in faces)


# ─── ומה שזה פותר ────────────────────────────────────────────────────────────

def test_the_font_is_served_from_our_own_origin(client):
    """זה מה שגורם לו להישמר במטמון של ה-Service Worker, כלומר לעבוד
    באופליין — הוא מיירט רק מקורות משלנו."""
    for url in re.findall(r"url\('([^']+)'\)", _CSS):
        assert url.startswith("/static/"), url


def test_the_font_css_is_cached_for_a_year_like_any_other_asset(client):
    """הוא נטען דרך url_for, אז הוא מקבל חתימה ואת אותה מדיניות מטמון —
    להבדיל מיום אחד בלבד אצל גוגל."""
    from flask import render_template_string
    with app.test_request_context("/"):
        url = render_template_string(
            "{{ url_for('static', filename='fonts/rubik.css') }}")

    assert "?v=" in url
    assert "max-age=31536000" in client.get(url).headers["Cache-Control"]
