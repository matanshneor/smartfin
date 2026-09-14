"""
בדיקות למנוע התנועות הקבועות — _recurring_occurrences.

זו הלוגיקה הכי מועדת לבאגים במערכת: היא רצה אוטומטית ברקע, יוצרת רשומות
כספיות, ואם היא טועה המשתמש רואה מספרים שגויים בתקציב בלי להבין למה.

הפונקציה טהורה (תבנית + תאריך פנימה, רשימת תאריכים החוצה), ולכן הבדיקות
האלה לא נוגעות ב-Supabase בכלל: אין התחברות, אין רשת, ואין סכנה למגבלת
ה-429. מכאן גם הסימון @pytest.mark.unit על כל הקובץ.
"""
from datetime import date

import pytest

from backend.supabase_config import _recurring_occurrences as occurrences

pytestmark = pytest.mark.unit


def _template(start, freq=None, end=None):
    """תבנית מינימלית — רק השדות ש-_recurring_occurrences באמת קורא."""
    tmpl = {"date": start}
    if freq:
        tmpl["recurring_frequency"] = freq
    if end:
        tmpl["recurring_end_date"] = end
    return tmpl


# ─── חודשי ביום־בחודש (monthly_same) ─────────────────────────────────────────

def test_monthly_same_clamps_to_short_month_then_recovers():
    """המקרה הקלאסי: תבנית מה-31 בינואר.

    פברואר חייב להתקצר ל-28, אבל מרץ חייב לחזור ל-31 — כלומר הקיצוץ נגזר
    מהחודש הנוכחי ולא "נדבק" לתבנית. זה בדיוק מה שרפקטור תמים עלול לשבור."""
    result = occurrences(_template("2026-01-31", "monthly_same"), date(2026, 7, 1))

    assert result == [
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
        date(2026, 5, 31),
        date(2026, 6, 30),
    ]


def test_monthly_same_hits_february_29_in_leap_year():
    """2028 היא שנה מעוברת — הקיצוץ חייב לתת 29 ולא 28."""
    result = occurrences(_template("2028-01-31", "monthly_same"), date(2028, 4, 1))

    assert result == [date(2028, 2, 29), date(2028, 3, 31)]


def test_monthly_same_excludes_the_template_date_itself():
    """תאריך המקור הוא התנועה שהמשתמש כבר הזין — אסור לייצר לו כפילות."""
    result = occurrences(_template("2026-03-10", "monthly_same"), date(2026, 5, 31))

    assert date(2026, 3, 10) not in result
    assert result == [date(2026, 4, 10), date(2026, 5, 10)]


# ─── חודשי בתאריך קבוע (monthly_1 / monthly_15) ──────────────────────────────

def test_monthly_1_skips_occurrence_before_start_date():
    """תבנית שנוצרה ב-15 בינואר בתדירות "ה-1 בחודש": ה-1 בינואר כבר עבר,
    אז המופע הראשון חייב להיות ה-1 בפברואר ולא ה-1 בינואר."""
    result = occurrences(_template("2026-01-15", "monthly_1"), date(2026, 4, 30))

    assert result == [date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)]


def test_monthly_15_starting_exactly_on_the_15th():
    """כשתאריך המקור הוא בדיוק היום היעד — המופע של אותו חודש נדלג
    (הוא התנועה המקורית), והספירה מתחילה מהחודש הבא."""
    result = occurrences(_template("2026-01-15", "monthly_15"), date(2026, 4, 30))

    assert result == [date(2026, 2, 15), date(2026, 3, 15), date(2026, 4, 15)]


def test_missing_frequency_falls_back_to_monthly_1():
    """תבנית ישנה בלי recurring_frequency לא אמורה להתפוצץ — ברירת המחדל
    בקוד היא monthly_1."""
    result = occurrences(_template("2026-01-10"), date(2026, 4, 1))

    assert result == [date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)]


# ─── שבועי ודו־שבועי ─────────────────────────────────────────────────────────

def test_weekly_steps_by_seven_days():
    result = occurrences(_template("2026-01-01", "weekly"), date(2026, 2, 1))

    assert result == [
        date(2026, 1, 8),
        date(2026, 1, 15),
        date(2026, 1, 22),
        date(2026, 1, 29),
    ]


def test_biweekly_crosses_the_year_boundary():
    """מעבר שנה — נקודה שבה חישובי תאריכים ידניים נוטים להישבר."""
    result = occurrences(_template("2025-12-20", "biweekly"), date(2026, 2, 1))

    assert result == [date(2026, 1, 3), date(2026, 1, 17), date(2026, 1, 31)]


# ─── גבולות: until ו-recurring_end_date ──────────────────────────────────────

def test_end_date_is_inclusive():
    """מופע שנופל בדיוק על recurring_end_date נכלל."""
    result = occurrences(
        _template("2026-01-01", "weekly", end="2026-01-22"), date(2026, 3, 1)
    )

    assert result[-1] == date(2026, 1, 22)


def test_until_is_inclusive():
    """אותו כלל עבור החסם העליון 'until' (בדרך כלל: היום)."""
    result = occurrences(_template("2026-01-01", "weekly"), date(2026, 1, 22))

    assert result[-1] == date(2026, 1, 22)


def test_end_date_before_first_occurrence_yields_nothing():
    result = occurrences(
        _template("2026-01-01", "monthly_same", end="2026-01-15"), date(2026, 6, 1)
    )

    assert result == []


def test_until_before_start_yields_nothing():
    """materialize_recurring מריץ עד היום — תבנית עתידית לא מייצרת כלום."""
    result = occurrences(_template("2026-05-01", "weekly"), date(2026, 1, 1))

    assert result == []


# ─── תקרת 500 המופעים ────────────────────────────────────────────────────────

def test_long_weekly_series_is_silently_truncated_at_500():
    """תיעוד התנהגות קיימת, לא אישור שלה.

    בקוד יש תקרה קשיחה של 500 מופעים. תבנית שבועית מ-2015 אמורה לייצר ~610
    מופעים — בפועל היא נעצרת ב-500, כלומר המופע האחרון הוא באוגוסט 2024
    ויותר משנתיים חסרות. אין שגיאה, אין לוג, והמשתמש רק רואה שהתנועה הקבועה
    שלו הפסיקה להופיע באמצע.

    אם התקרה תוסר או תלווה בהתראה — הבדיקה הזאת תיפול, וזו בדיוק הכוונה."""
    result = occurrences(_template("2015-01-01", "weekly"), date(2026, 9, 14))

    assert len(result) == 500
    assert result[-1] == date(2024, 8, 1)
    assert result[-1] < date(2026, 9, 14), "התקרה עוצרת את הסדרה הרחק בעבר"


def test_monthly_series_stays_under_the_cap():
    """בקרת-נגד: תדירות חודשית לא מגיעה לתקרה גם על פני עשורים, כך שהבעיה
    ממוקדת בתדירויות הצפופות (שבועי ודו-שבועי)."""
    result = occurrences(_template("1990-01-01", "monthly_1"), date(2026, 9, 14))

    assert len(result) < 500
    assert result[-1] == date(2026, 9, 1)
