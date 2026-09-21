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

def _demo_numbers():
    """המספרים שמוצגים במוקאפ: ההוצאה על מזון והאחוז שבהתראה."""
    spend = int(re.search(r"מזון</span><b>₪([\d,]+)</b>", _HTML).group(1).replace(",", ""))
    pct   = int(re.search(r"(\d+)% מעל הממוצע", _HTML).group(1))
    return spend, pct


def test_the_example_would_actually_fire():
    """הלב. הסף האמיתי הוא שני תנאים יחד, ו-18% לא עבר אף אחד מהם."""
    _, pct = _demo_numbers()
    threshold = db.DEFAULT_FAMILY_SETTINGS["anomaly"]["percent"] - 100

    assert pct > threshold, f"{pct}% לא מפעיל התראה — הסף הוא {threshold}%"


def test_the_example_also_clears_the_shekel_gap():
    """התנאי השני, שקל ולא אחוז: קטגוריה קטנה יכולה לקפוץ ב-80% ועדיין
    לא להצדיק התראה."""
    spend, pct = _demo_numbers()
    avg = spend / (1 + pct / 100)
    min_gap = db.DEFAULT_FAMILY_SETTINGS["anomaly"]["min_gap"]

    assert spend - avg >= min_gap, f"פער של ₪{spend - avg:,.0f} מתחת ל-₪{min_gap}"


def test_the_numbers_stay_tied_to_the_real_default():
    """בקרת-נגד: אם ברירת המחדל של הסף תשתנה, הבדיקות למעלה ייפלו —
    ולא יישאר דף שיווק שמבטיח משהו אחר מהמוצר."""
    anomaly = db.DEFAULT_FAMILY_SETTINGS["anomaly"]

    assert anomaly["percent"] == 150
    assert anomaly["min_gap"] == 300
