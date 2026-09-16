"""
בדיקות ניגודיות.

הזהב של SmartFin (#A67C00) נתן 3.82:1 על לבן — מתחת ל-4.5 שהתקן דורש
לטקסט רגיל. זה נגע בכל האפליקציה, וגם בכפתור הראשי: לבן על הקצה הבהיר
של הגרדיאנט נתן 2.75:1, וזה הכפתור של התחברות, הרשמה ואשף ההגדרה.

הפתרון שנבחר: הזהב עצמו נשאר לאייקונים, מסגרות וקווים — שם התקן דורש
3:1 והוא עובר — ואסימון כהה יותר משמש לטקסט בלבד, כך שהזהות החזותית
לא זזה.

הבדיקות מחשבות את היחס מתוך ה-CSS עצמו ולא מקבעות מספרים, כדי שכל
שינוי עתידי בפלטה ייבדק מחדש.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_CSS = (Path(__file__).resolve().parent.parent
        / "frontend/static/css/style.css").read_text(encoding="utf-8")


def _token(name):
    m = re.search(rf"--{name}:\s*(#[0-9A-Fa-f]{{6}})", _CSS)
    assert m, f"לא נמצא האסימון --{name}"
    return m.group(1)


def _gradient_stops():
    m = re.search(r"--gradient-gold:\s*[^;]*?(#[0-9A-Fa-f]{6})[^;]*?(#[0-9A-Fa-f]{6})", _CSS)
    assert m, "לא נמצא הגרדיאנט"
    return m.group(1), m.group(2)


def _luminance(hexstr):
    channels = (int(hexstr[i:i + 2], 16) / 255 for i in (1, 3, 5))
    def linear(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (linear(c) for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ratio(a, b):
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _over(fg, bg, alpha):
    """צבע שקוף מעל רקע אטום — מה שהעין באמת רואה."""
    f = [int(fg[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02X%02X%02X" % tuple(round(f[i] * alpha + b[i] * (1 - alpha)) for i in range(3))


WHITE = "#FFFFFF"


# ─── טקסט: 4.5:1 ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("surface,name", [
    (WHITE,                "כרטיס לבן"),
    (None,                 "רקע העמוד"),
])
def test_gold_text_is_readable(surface, name):
    bg = surface or _token("color-bg")
    r = _ratio(_token("color-gold-text"), bg)

    assert r >= 4.5, f"טקסט זהב על {name}: {r:.2f}:1"


def test_gold_text_on_a_tinted_badge_is_readable():
    """המקרה הקשה, וזה שקל לפספס: תגית עם רקע זהב בשקיפות 10%, מעל רקע
    העמוד. חישוב מול לבן בלבד היה עובר ומשאיר את זה שבור."""
    tinted = _over(_token("color-gold"), _token("color-bg"), 0.10)
    r = _ratio(_token("color-gold-text"), tinted)

    assert r >= 4.5, f"{r:.2f}:1"


@pytest.mark.parametrize("stop", [0, 1])
def test_white_on_the_primary_button_is_readable(stop):
    """גרדיאנט נבדק בשני קצותיו — הבהיר הוא זה שנכשל."""
    r = _ratio(WHITE, _gradient_stops()[stop])

    assert r >= 4.5, f"קצה {stop}: {r:.2f}:1"


def test_muted_text_is_readable():
    r = _ratio(_token("color-text-muted"), WHITE)
    assert r >= 4.5, f"{r:.2f}:1"


# ─── לא-טקסט: 3:1 ────────────────────────────────────────────────────────────

def test_borders_and_icons_keep_the_brand_gold():
    """בקרת-נגד: הזהב המקורי נשאר, ועובר את הדרישה לתוכן שאינו טקסט.
    בלי זה 'תיקנו נגישות' היה אומר 'שינינו את המראה של האפליקציה'."""
    gold = _token("color-gold")

    assert gold == "#A67C00", "גוון המותג השתנה"
    assert _ratio(gold, WHITE) >= 3.0


def test_nothing_still_uses_the_brand_gold_as_text():
    """‎color:‎ הוא טקסט; מסגרות ומילויים משתמשים במאפיינים אחרים."""
    leftovers = re.findall(r"(?<![-\w])color:\s*var\(--color-gold\)", _CSS)

    assert not leftovers, f"{len(leftovers)} שימושים בזהב המותג כטקסט"


# ─── שאר הפלטה ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("token,what", [
    ("color-savings", "סכומי חיסכון"),
    ("color-income",  "סכומי הכנסה"),
    ("color-expense", "סכומי הוצאה"),
    ("color-text",    "טקסט רגיל"),
    ("color-text-soft", "טקסט משני"),
])
def test_every_colour_used_for_money_is_readable(token, what):
    """סכומים הם הטקסט שהכי חשוב שייקרא נכון באפליקציה הזאת."""
    for bg, name in ((WHITE, "כרטיס"), (_token("color-bg"), "רקע העמוד")):
        r = _ratio(_token(token), bg)
        assert r >= 4.5, f"{what} על {name}: {r:.2f}:1"


@pytest.mark.parametrize("token", [
    "color-expense-light", "color-income-light", "color-savings-light",
])
def test_the_light_variants_are_checked_against_the_dark_hero(token):
    """הם משמשים רק בתוך ה-KPI על הרקע הכהה. השוואה מול לבן הייתה
    מראה כשל מדומה ושולחת לתקן צבע תקין."""
    r = _ratio(_token(token), _token("hero-bg"))

    assert r >= 4.5, f"{r:.2f}:1"


def test_the_hero_text_is_checked_against_the_hero():
    r = _ratio(_token("hero-text"), _token("hero-bg"))
    assert r >= 4.5, f"{r:.2f}:1"
