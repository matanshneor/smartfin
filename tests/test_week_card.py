"""כרטיס "השבוע" בדף הבית (מתן, 30.9).

הוצאות הבית בלבד — בלי פרויקטים ובלי עסקאות קבועות (יום אחד של שכר דירה
היה מגמד את כל השבוע). ראשון עד שבת. ההשוואה לשבוע שעבר — עד אותו יום
בשבוע, כדי שיום רביעי לא יושווה לשבוע שלם.
"""
import datetime

import pytest

from backend import supabase_config as db
from tests._fake_db import FakeSupabase

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"
_WED = datetime.date(2026, 10, 7)          # יום רביעי; השבוע: 4.10–10.10


def _tx(amount, date, desc="", cat="food", recurring=False, parent=None, project=None, type_="expense"):
    return {"id": f"{amount}-{date}-{desc}", "family_id": _FAM, "amount": amount, "type": type_,
            "date": date, "description": desc, "category_id": cat, "project_id": project,
            "is_recurring": recurring, "recurring_parent_id": parent,
            "categories": {"name": "סופר" if cat == "food" else "דלק", "icon": "🛒" if cat == "food" else "⛽"}}


def _week(rows, monkeypatch, today=_WED):
    monkeypatch.setattr(db, "get_client", lambda: FakeSupabase(transactions=rows))
    return db.week_spending(_FAM, today=today)


def test_seven_days_sunday_first_with_today_and_future(monkeypatch):
    w = _week([], monkeypatch)
    assert [d["date"] for d in w["days"]] == [f"2026-10-{d:02d}" for d in range(4, 11)]
    assert [d["label"] for d in w["days"]] == ["א׳", "ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "ש׳"]
    assert [d["today"] for d in w["days"]].index(True) == 3
    assert [d["future"] for d in w["days"]] == [False] * 4 + [True] * 3


def test_totals_per_day_and_for_the_week(monkeypatch):
    w = _week([_tx(180, "2026-10-04", "מסעדה"), _tx(412, "2026-10-05"), _tx(250, "2026-10-05", cat="fuel"),
               _tx(32, "2026-10-07")], monkeypatch)
    assert [d["total"] for d in w["days"][:4]] == [180, 662, 0, 32]
    assert w["total"] == 874
    monday = w["days"][1]["transactions"]
    assert {(t["icon"], t["name"], t["amount"]) for t in monday} == {("🛒", "סופר", 412), ("⛽", "דלק", 250)}


def test_recurring_projects_and_income_are_left_out(monkeypatch):
    w = _week([_tx(100, "2026-10-05"),
               _tx(5500, "2026-10-04", "שכר דירה", recurring=True),
               _tx(120, "2026-10-05", "סלולר", parent="tpl-1"),
               _tx(4000, "2026-10-06", "קבלן", project="p1"),
               _tx(9000, "2026-10-04", "משכורת", type_="income")], monkeypatch)
    assert w["total"] == 100


def test_compared_with_last_week_up_to_the_same_day(monkeypatch):
    """רביעי מול ראשון–רביעי של שבוע שעבר; חמישי שעבר לא נספר."""
    w = _week([_tx(300, "2026-10-05"),
               _tx(500, "2026-09-28"), _tx(200, "2026-09-30"),
               _tx(900, "2026-10-01")], monkeypatch)          # חמישי שעבר — מחוץ להשוואה
    assert w["last_week"] == 700 and w["diff"] == -400


def test_no_comparison_without_last_week_data(monkeypatch):
    assert _week([_tx(300, "2026-10-05")], monkeypatch)["last_week"] is None


def test_saturday_closes_the_week_and_sunday_opens_a_new_one(monkeypatch):
    sat = _week([_tx(50, "2026-10-10")], monkeypatch, today=datetime.date(2026, 10, 10))
    assert sat["days"][-1]["today"] and sat["total"] == 50
    sun = _week([_tx(50, "2026-10-10")], monkeypatch, today=datetime.date(2026, 10, 11))
    # ביום ראשון ההשוואה היא רק לראשון שעבר — השבת שלפניו כבר שבוע שלם אחר
    assert sun["days"][0]["date"] == "2026-10-11" and sun["total"] == 0 and sun["last_week"] is None


def test_the_card_is_placed_under_the_three_cards_and_days_can_be_tapped():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    tpl = (root / "frontend/templates/index.html").read_text(encoding="utf-8")
    assert tpl.index('class="summary-cards"') < tpl.index('class="chart-card week-card"') < tpl.index("<h2>עסקאות אחרונות</h2>")
    js = (root / "frontend/static/js/core.js").read_text(encoding="utf-8")
    assert "d.hidden = d.dataset.day !== btn.dataset.day;" in js


def test_an_empty_day_says_so_in_matans_words():
    """יום עבר בלי עסקאות: "ביום זה"; היום עצמו: "היום" (מתן, 1.10)."""
    from pathlib import Path
    import jinja2
    tpl = (Path(__file__).resolve().parent.parent / "frontend/templates/index.html").read_text(encoding="utf-8")
    start = tpl.index("{% for d in week.days if not d.future %}")
    snippet = tpl[start:tpl.index("{% endfor %}", tpl.index('class="week-empty"')) + len("{% endfor %}")]
    env = jinja2.Environment()
    env.filters["money"] = lambda v: v
    day = {"label": "ה׳", "day": 1, "month": 10, "total": 0, "transactions": [], "future": False}
    html = env.from_string(snippet).render(week={"days": [dict(day, today=False), dict(day, today=True)]})
    assert html.count('<p class="week-empty">לא בוצעו עסקאות ביום זה</p>') == 1
    assert html.count('<p class="week-empty">לא בוצעו עסקאות היום</p>') == 1
