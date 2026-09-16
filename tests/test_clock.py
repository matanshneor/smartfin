"""
בדיקות לשעון האפליקציה.

השרת רץ ב-Railway בשעון UTC והמשתמשים בישראל. הדפדפן חותם עסקה חדשה
בשעון המקומי, בזמן שהשרת החליט לפי השעון שלו איזה חודש להציג — ובין
חצות לשלוש לפנות בוקר השניים לא מסכימים.

התרחיש שכאב: ב-00:30 ב-1 בספטמבר, שעון ישראל. השרת ב-UTC עדיין ב-31
באוגוסט, ולכן מגיש דשבורד של אוגוסט. המשתמש מוסיף קנייה של ₪500,
הדפדפן חותם אותה 2026-09-01, והיא פשוט לא מופיעה — עד שהיא "צצה משום
מקום" שלוש שעות אחר כך. זה חוזר בכל מעבר חודש.
"""
from datetime import datetime, timezone

import pytest

from backend import clock

pytestmark = pytest.mark.unit


def _at_utc(monkeypatch, iso_utc: str):
    """מקפיא את השעון ברגע מסוים ב-UTC, כמו שהשרת בפרודקשן חווה אותו."""
    frozen = datetime.fromisoformat(iso_utc).replace(tzinfo=timezone.utc)

    class _DT(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen.astimezone(tz) if tz else frozen.replace(tzinfo=None)

    monkeypatch.setattr(clock, "datetime", _DT)


# ─── התרחיש שכאב ─────────────────────────────────────────────────────────────

def test_just_after_midnight_the_server_is_in_the_same_month_as_the_phone(monkeypatch):
    """00:30 ב-1 בספטמבר בישראל = 21:30 ב-31 באוגוסט ב-UTC.
    לפני התיקון השרת הגיש אוגוסט בזמן שהטלפון כבר בספטמבר."""
    _at_utc(monkeypatch, "2026-08-31T21:30:00")

    assert clock.today().month == 9, "השרת עדיין בחודש הקודם — עסקאות ייעלמו"
    assert clock.today().day == 1


def test_late_at_night_the_server_is_on_the_same_day_as_the_phone(monkeypatch):
    """לא רק מעבר חודש: כל לילה בין חצות לשלוש 'היום' של השרת פיגר ביום."""
    _at_utc(monkeypatch, "2026-09-15T22:10:00")   # 01:10 ב-16/09 בישראל

    assert clock.today().day == 16


# ─── מעברי שעון הקיץ ─────────────────────────────────────────────────────────
#
# בישראל המעבר הוא בשישי האחרון של מרץ ובראשון האחרון של אוקטובר — לא
# כמו אירופה ולא כמו ארה"ב. לכן ההיסט נגזר מ-ZoneInfo ולא מקודד ידנית.

@pytest.mark.parametrize("utc_moment,expected_hour", [
    ("2026-03-26T12:00:00", 14),   # לפני המעבר — חורף, UTC+2
    ("2026-03-28T12:00:00", 15),   # אחרי המעבר — קיץ, UTC+3
    ("2026-10-24T12:00:00", 15),   # עדיין קיץ
    ("2026-10-26T12:00:00", 14),   # חזרה לחורף
])
def test_the_offset_follows_israeli_daylight_saving(monkeypatch, utc_moment, expected_hour):
    _at_utc(monkeypatch, utc_moment)

    assert clock.now().hour == expected_hour


# ─── שהשעון באמת בשימוש ──────────────────────────────────────────────────────

def test_no_server_code_still_asks_the_container_for_the_time():
    """תיקון נקודתי לא שווה כלום כאן: מספיק מקום אחד שנשכח כדי שחודש
    יחושב בשעון הלא נכון. הבדיקה סורקת את הקוד כולו."""
    from pathlib import Path
    import re

    backend = Path(__file__).resolve().parent.parent / "backend"
    offenders = []
    for f in backend.glob("*.py"):
        if f.name == "clock.py":
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
            if re.search(r"\bdatetime\.now\(\)|\bdate\.today\(\)|utcnow\(", line):
                offenders.append(f"{f.name}:{n}")

    assert not offenders, f"שעון המכולה עדיין בשימוש ב: {offenders}"


def test_the_timezone_is_pinned_to_israel():
    assert str(clock.ISRAEL) == "Asia/Jerusalem"


def test_the_clock_returns_naive_values(monkeypatch):
    """הקוד הקיים משווה datetime ללא אזור; ערבוב עם aware מרים TypeError
    באמצע עמוד. הבחירה מכוונת ולכן נבדקת."""
    _at_utc(monkeypatch, "2026-09-16T08:00:00")

    assert clock.now().tzinfo is None
