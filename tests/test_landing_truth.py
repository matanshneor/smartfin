"""
דף הנחיתה הבטיח שני דברים שהמוצר לא מקיים.

**חודש מקודד.** "ספטמבר 2026" נכתב קשיח במוקאפ. נכון ליום שנכתב,
ושגוי מ-1 באוקטובר — ותאריך ישן בדף שיווק קורא כמו פרויקט נטוש.

**התראה ברגישות שלא קיימת.** הדוגמה המרכזית הציגה "18% מעל הממוצע",
בעוד שההתראה האמיתית קופצת רק מ-50% מעל ממוצע שלושת החודשים **וגם**
₪300 מעליו. כלומר הדגמנו תכונה שלא תעבוד — ומי שנרשם בגללה היה מחכה
להתראה שלא תגיע.
"""
import re
from pathlib import Path

import pytest

from backend import clock, supabase_config as db
from backend.app import app, _month_label

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_HTML = (_ROOT / "frontend/templates/landing.html").read_text(encoding="utf-8")


@pytest.fixture
def anon():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ─── החודש ──────────────────────────────────────────────────────────────────

def test_the_month_is_not_hard_coded():
    assert "ספטמבר 2026" not in _HTML
    assert "{{ demo_month }}" in _HTML


def test_the_landing_page_shows_the_current_month(anon):
    """נגזר מאותו שעון ישראל של כל שאר האפליקציה."""
    html = anon.get("/?intro=1").get_data(as_text=True)
    now = clock.now()

    assert _month_label(now.year, now.month) in html


# ─── ההתראה ─────────────────────────────────────────────────────────────────
#
# מאז 11.10 התראה על קטגוריה היא רק חריגה מתקציב (התראת "מעל הממוצע" הוסרה
# מהמוצר). המוקאפ חייב להראות התראה שהמוצר באמת יורה — עם המספרים שלו.

def _demo_numbers():
    """המספרים שמוצגים במוקאפ: ההוצאה על מזון, והתקציב והחריגה שבהתראה."""
    spend = int(re.search(r"מזון</span><b>₪([\d,]+)</b>", _HTML).group(1).replace(",", ""))
    m = re.search(r"₪([\d,]+) מתוך תקציב של ₪([\d,]+) — חריגה של ₪([\d,]+)", _HTML)
    alert_spend, budget, excess = (int(g.replace(",", "")) for g in m.groups())
    return spend, alert_spend, budget, excess


def test_the_example_would_actually_fire():
    spend, alert_spend, budget, excess = _demo_numbers()
    assert alert_spend == spend, "ההתראה מדברת על סכום אחר מזה שבמוקאפ"
    assert spend > budget and excess == spend - budget


def test_the_alert_text_is_the_products_own_wording():
    """אותו ניסוח כמו ‎db.budget_alerts‎ — לא ניסוח שיווקי שהמוצר לא מראה."""
    spend, _, budget, _ = _demo_numbers()
    row = {"category_id": "c", "name": "מזון", "icon": "🛒", "total": spend}
    text = db.budget_alerts(db.apply_budgets([row], {"limits": {"c": {"amount": budget}}}))[0]["text"]
    assert text.split(": ", 1)[1] in _HTML


def test_nothing_promises_the_removed_average_alert():
    visible = re.sub(r"\{#.*?#\}", "", _HTML, flags=re.S)
    assert "מעל הממוצע" not in visible and "מהממוצע" not in visible
