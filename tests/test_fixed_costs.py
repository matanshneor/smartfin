"""
בדיקות לתצוגת "קבוע כל חודש".

ההוצאות הקבועות — משכורת, שכירות, מנויים, ביטוח — היו באפליקציה אבל
קבורות באקורדיון סגור בהגדרות. שום מסך לא ענה על "כמה יוצא לנו כל חודש
בלי קשר למה שנעשה", וזה המספר הכי שימושי בתקציב ביתי: הוא מה שלא משתנה,
ולכן מה שאפשר לתכנן סביבו.

הנרמול הוא העיקר. שבועי הוא 52/12 ולא 4, ודו-שבועי 26/12 ולא 2 — ההפרש
הוא כמעט חודש שלם בשנה, ועל שכירות זה סכום אמיתי.
"""
import datetime

import pytest

from backend import supabase_config as db

pytestmark = pytest.mark.unit

_TODAY = datetime.date(2026, 9, 16)


def _row(amount, **kw):
    base = {"amount": amount, "type": "expense", "recurring_frequency": "monthly_1",
            "description": "x", "recurring_end_date": None}
    base.update(kw)
    return base


def _sum(rows):
    return db.summarise_recurring(rows, today=_TODAY)


# ─── הנרמול ──────────────────────────────────────────────────────────────────

def test_a_monthly_amount_counts_once():
    assert _sum([_row(5200)])["expense"] == pytest.approx(5200)


def test_a_weekly_amount_is_not_multiplied_by_four():
    """52/12 = 4.33, לא 4. ההפרש על ₪300 בשבוע הוא ₪1,200 בשנה."""
    result = _sum([_row(300, recurring_frequency="weekly")])["expense"]

    assert result == pytest.approx(300 * 52 / 12)
    assert result != pytest.approx(300 * 4)


def test_a_biweekly_amount_is_not_multiplied_by_two():
    result = _sum([_row(500, recurring_frequency="biweekly")])["expense"]

    assert result == pytest.approx(500 * 26 / 12)


@pytest.mark.parametrize("freq", ["monthly_same", "monthly_1", "monthly_15"])
def test_all_the_monthly_variants_count_once(freq):
    assert _sum([_row(100, recurring_frequency=freq)])["expense"] == pytest.approx(100)


def test_an_unknown_frequency_falls_back_to_monthly():
    """עדיף להציג פעם אחת מלהתעלם או להכפיל בגורם שהומצא."""
    assert _sum([_row(100, recurring_frequency="quarterly")])["expense"] == pytest.approx(100)


# ─── מה נספר ומה לא ──────────────────────────────────────────────────────────

def test_a_template_that_already_ended_is_not_counted():
    """מנוי שבוטל אינו הוצאה קבועה, וספירתו מנפחת את התמונה."""
    rows = [_row(5200), _row(99, recurring_end_date="2026-01-01")]
    result = _sum(rows)

    assert result["expense"] == pytest.approx(5200)
    assert len(result["rows"]) == 1


def test_a_template_ending_later_still_counts():
    """בקרת-נגד: תאריך סיום עתידי עדיין קבוע היום."""
    assert _sum([_row(99, recurring_end_date="2027-01-01")])["expense"] == pytest.approx(99)


def test_income_and_savings_are_kept_apart_from_expenses():
    """משכורת קבועה שנספרת כהוצאה הופכת את המספר לחסר משמעות."""
    rows = [_row(5200), _row(14000, type="income"), _row(1000, type="savings")]
    result = _sum(rows)

    assert result["expense"] == pytest.approx(5200)
    assert result["income"] == pytest.approx(14000)
    assert result["savings"] == pytest.approx(1000)


def test_the_biggest_commitment_comes_first():
    """מי שפותח את הכרטיס רוצה לדעת מה הכי כבד."""
    rows = [_row(80), _row(5200), _row(300, recurring_frequency="weekly")]

    assert [r["amount"] for r in _sum(rows)["rows"]] == [5200, 300, 80]


def test_nothing_recurring_produces_nothing_to_show():
    result = _sum([])

    assert result["rows"] == []
    assert result["expense"] == 0


# ─── התצוגה ──────────────────────────────────────────────────────────────────

def test_the_key_is_not_called_items():
    """‎fixed.items‎ ב-Jinja מחזיר את מתודת המילון ולא את הרשימה, והלולאה
    מתפוצצת. השם הזה חייב להישאר שונה."""
    assert "rows" in _sum([_row(1)])
    assert "items" not in _sum([_row(1)])


def test_a_non_monthly_row_also_shows_its_original_amount():
    """בלי זה ‎₪1,300‎ על הוצאה של ₪300 בשבוע נראה כמו טעות חישוב."""
    from pathlib import Path
    html = (Path(__file__).resolve().parent.parent
            / "frontend/templates/month.html").read_text(encoding="utf-8")
    block = html[html.index("קבוע כל חודש"):][:2000]

    assert "item.per_month != 1.0" in block
    assert "item.amount" in block and "item.monthly_amount" in block


def test_the_card_is_only_built_for_the_current_month():
    """"ההוצאות הקבועות שלנו" הוא מספר של עכשיו. לחודש שעבר הוא היה
    משהו אחר שאין לנו דרך לשחזר, והצגת המספר הנוכחי שם היא שקר."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent
           / "backend/app.py").read_text(encoding="utf-8")
    block = src[src.index('p2_tasks["run_rate"]'):][:600]

    assert 'p2_tasks["recurring"]' in block, "הוזז מחוץ לתנאי is_current"
