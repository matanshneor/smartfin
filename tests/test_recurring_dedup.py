"""הדדופ של העסקאות הקבועות — הלוגיקה שמונעת כסף כפול.

זו הפונקציה שעומדת בין המשפחה לבין הכפלת המשכורת. היא לא הייתה מכוסה
בשום בדיקה ישירה: הכיסוי היחיד היה דרך ‎materialize_recurring‎ מלאה,
שדורשת מסד, ולכן לא רצה בשום מקום.

הבאג המקורי שהיא נולדה כדי למנוע: הדדופ השווה תאריכים **מדויקים**. מי
ששינה בתבנית את יום המשכורת מה-5 ל-10 בחודש קיבל סדרת תאריכים חדשה
שאף אחד ממנה לא היה מוכר — וכל החודשים אחורה נוצרו מחדש. ₪14,000 כפול
שמונה חודשים, בבת אחת, בכל מסך באפליקציה.

הפונקציות טהורות, אז הבדיקות כאן הן ערכים מול ערכים.
"""
from datetime import date

import pytest

from backend.supabase_config import (_already_materialized, _occurrence_period,
                                     _recurring_occurrences)

pytestmark = pytest.mark.unit


def _d(s):
    return date.fromisoformat(s)


# ═══ חודשי: התקופה היא החודש, לא היום ════════════════════════════════════════

@pytest.mark.parametrize("freq", ["monthly_1", "monthly_15", "monthly_same"])
def test_the_same_month_on_a_different_day_is_the_same_occurrence(freq):
    """הלב. זה בדיוק המקרה שהכפיל את המשכורת: אותו חודש, יום אחר."""
    assert _already_materialized(freq, _d("2026-09-10"), [_d("2026-09-05")]) is True


@pytest.mark.parametrize("freq", ["monthly_1", "monthly_15", "monthly_same"])
def test_a_different_month_is_a_new_occurrence(freq):
    """בקרת-נגד, וחשובה לא פחות: דדופ רחב מדי בולע משכורות אמיתיות."""
    assert _already_materialized(freq, _d("2026-10-05"), [_d("2026-09-05")]) is False


def test_the_same_day_number_in_another_year_is_not_the_same_month():
    assert _already_materialized("monthly_1", _d("2027-09-05"), [_d("2026-09-05")]) is False


def test_nothing_existing_means_nothing_was_materialized():
    assert _already_materialized("monthly_1", _d("2026-09-05"), []) is False


def test_the_period_key_is_the_calendar_month():
    assert _occurrence_period("monthly_1", _d("2026-09-30")) == (2026, 9)
    assert _occurrence_period("monthly_1", _d("2026-09-01")) == (2026, 9)
    assert _occurrence_period("monthly_1", _d("2026-10-01")) != (2026, 9)


# ═══ שבועי ודו-שבועי: אין "תקופה", אז מרחק ═══════════════════════════════════

@pytest.mark.parametrize("gap,same", [(0, True), (3, True), (4, False), (10, False)])
def test_weekly_treats_a_shift_of_up_to_three_days_as_the_same_occurrence(gap, same):
    """תבנית שבועית שזזה ביום-יומיים היא אותו תשלום שרק הוזז."""
    from datetime import timedelta
    existing = _d("2026-09-07")
    assert _already_materialized("weekly", existing + timedelta(days=gap), [existing]) is same


@pytest.mark.parametrize("gap,same", [(0, True), (7, True), (8, False), (14, False)])
def test_biweekly_allows_a_wider_shift(gap, same):
    from datetime import timedelta
    existing = _d("2026-09-07")
    assert _already_materialized("biweekly", existing + timedelta(days=gap), [existing]) is same


def test_a_weekly_shift_is_measured_in_both_directions():
    """מופע שהוקדם הוא אותו מופע כמו מופע שנדחה."""
    assert _already_materialized("weekly", _d("2026-09-05"), [_d("2026-09-07")]) is True


# ═══ ייצור המופעים עצמם ══════════════════════════════════════════════════════

def _template(**kw):
    row = {"date": "2026-01-15", "recurring_frequency": "monthly_same"}
    row.update(kw)
    return row


def test_occurrences_stop_at_the_end_date():
    """תאריך סיום שלא נאכף מייצר הוצאה קבועה שכבר הסתיימה, לנצח."""
    dates = _recurring_occurrences(
        _template(date="2026-01-15", recurring_end_date="2026-03-31"), _d("2026-12-31"))

    assert max(dates) <= _d("2026-03-31")


def test_occurrences_stop_at_today():
    """מופעים עתידיים אינם עובדה — הם עוד לא קרו."""
    dates = _recurring_occurrences(_template(date="2026-01-15"), _d("2026-04-30"))

    assert max(dates) <= _d("2026-04-30")


def test_a_monthly_series_produces_one_occurrence_per_month():
    dates = _recurring_occurrences(_template(date="2026-01-15"), _d("2026-04-30"))

    assert sorted({(d.year, d.month) for d in dates}) == [(2026, 2), (2026, 3), (2026, 4)]
    assert len(dates) == len(set(dates)), "אותו תאריך נוצר פעמיים"


def test_a_day_that_does_not_exist_in_the_month_is_clamped():
    """ה-31 בכל חודש: פברואר אין בו 31, ובלי הקיצוץ זו קריסה."""
    dates = _recurring_occurrences(
        _template(date="2026-01-31", recurring_frequency="monthly_same"), _d("2026-03-31"))

    february = [d for d in dates if d.month == 2]
    assert february == [_d("2026-02-28")], february


def test_the_series_cannot_run_away():
    """התקרה שעמדה בין תאריך שגוי לבין 500 עסקאות אמיתיות בקריאה אחת.
    היא עדיין שם — אבל עכשיו ‎_parse_date‎ עוצר לפניה."""
    dates = _recurring_occurrences(_template(date="1900-01-15"), _d("2026-09-30"))

    assert len(dates) <= 500


def test_the_template_date_itself_is_not_an_occurrence():
    """המופע הראשון הוא העסקה עצמה. ייצור שלו שוב הוא כפילות."""
    dates = _recurring_occurrences(_template(date="2026-01-15"), _d("2026-04-30"))

    assert _d("2026-01-15") not in dates
