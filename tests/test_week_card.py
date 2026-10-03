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
    assert tpl.index('class="summary-cards"') < tpl.index('{% include "_week_card.html" %}') < tpl.index("<h2>עסקאות אחרונות</h2>")
    js = (root / "frontend/static/js/core.js").read_text(encoding="utf-8")
    assert "d.hidden = d.dataset.day !== btn.dataset.day;" in js


def test_an_empty_day_says_so_in_matans_words():
    """יום עבר בלי עסקאות: "ביום זה"; היום עצמו: "היום" (מתן, 1.10)."""
    from pathlib import Path
    import jinja2
    tpl = (Path(__file__).resolve().parent.parent / "frontend/templates/_week_card.html").read_text(encoding="utf-8")
    start = tpl.index("{% for d in week.days if not d.future %}")
    snippet = tpl[start:tpl.index("{% endfor %}", tpl.index('class="week-empty"')) + len("{% endfor %}")]
    env = jinja2.Environment()
    env.filters["money"] = lambda v: v
    day = {"label": "ה׳", "day": 1, "month": 10, "total": 0, "transactions": [], "future": False}
    html = env.from_string(snippet).render(week={"days": [dict(day, today=False, selected=False),
                                                          dict(day, today=True, selected=True)]})
    assert html.count('<p class="week-empty">לא בוצעו עסקאות ביום זה</p>') == 1
    assert html.count('<p class="week-empty">לא בוצעו עסקאות היום</p>') == 1



# ─── דפדוף לשבועות קודמים (מתן, 2.10) ─────────────────────────────────────

def _past(rows, monkeypatch, offset):
    monkeypatch.setattr(db, "get_client", lambda: FakeSupabase(transactions=rows))
    return db.week_spending(_FAM, today=_WED, offset=offset)


def test_last_week_is_shown_whole_and_compared_with_the_week_before(monkeypatch):
    # השבוע: 4.10–10.10. שבוע שעבר: 27.9–3.10. לפניו: 20.9–26.9
    w = _past([_tx(100, "2026-10-03"), _tx(40, "2026-09-28"), _tx(60, "2026-09-22")], monkeypatch, 1)
    assert [d["date"] for d in w["days"]] == ["2026-09-27", "2026-09-28", "2026-09-29", "2026-09-30",
                                              "2026-10-01", "2026-10-02", "2026-10-03"]
    assert not any(d["future"] or d["today"] for d in w["days"]), "שבוע שעבר שלם"
    assert w["total"] == 140 and w["last_week"] == 60 and w["diff"] == 80
    assert w["offset"] == 1


def test_a_past_week_opens_on_its_last_day_with_spending(monkeypatch):
    w = _past([_tx(40, "2026-09-28"), _tx(30, "2026-09-30")], monkeypatch, 1)
    assert [d["selected"] for d in w["days"]].index(True) == 3        # רביעי 30.9
    empty = _past([], monkeypatch, 1)
    assert [d["selected"] for d in empty["days"]].index(True) == 6    # בלי הוצאות — שבת


def test_this_week_opens_on_today(monkeypatch):
    w = _week([_tx(40, "2026-10-04")], monkeypatch)
    assert [d["selected"] for d in w["days"]].index(True) == 3


def test_older_is_offered_only_when_there_is_something_older(monkeypatch):
    assert _past([_tx(40, "2026-09-28")], monkeypatch, 0)["has_older"] is True
    assert _past([_tx(40, "2026-09-28")], monkeypatch, 1)["has_older"] is False
    # עסקה קבועה ופרויקט לא נספרים — כמו בכרטיס עצמו
    rows = [_tx(5000, "2026-09-01", recurring=True), _tx(90, "2026-09-02", project="p1")]
    assert _past(rows, monkeypatch, 0)["has_older"] is False


def test_the_card_title_and_arrows_follow_the_offset():
    from pathlib import Path
    from backend.app import app
    tpl = (Path(__file__).resolve().parent.parent / "frontend/templates/_week_card.html").read_text(encoding="utf-8")
    day = {"label": "א׳", "day": 1, "month": 10, "total": 0, "transactions": [], "future": False,
           "today": False, "selected": False}
    def render(offset, has_older):
        with app.test_request_context():
            return app.jinja_env.from_string(tpl).render(week={
                "days": [dict(day)] * 7, "total": 0, "diff": None, "max": 0,
                "offset": offset, "has_older": has_older})
    now, last, old = render(0, True), render(1, True), render(3, False)
    assert ">השבוע</h2>" in now and ">שבוע שעבר</h2>" in last and ">לפני 3 שבועות</h2>" in old
    assert 'data-week-go="-1" aria-label="שבוע הבא"\n                    disabled' in now, "אין שבוע הבא אחרי השבוע"
    assert 'data-week-go="4" aria-label="שבוע קודם"\n                    disabled' in old, "אין ישן יותר"


def test_the_week_route_returns_the_card_and_refuses_nonsense(monkeypatch):
    from backend import app as app_module
    from backend.app import app, limiter
    limiter.reset()
    app.config["TESTING"] = True
    seen = []
    real = db.week_spending
    monkeypatch.setattr(db, "get_client", lambda: FakeSupabase(transactions=[_tx(40, "2026-09-28")]))
    monkeypatch.setattr(app_module.db, "week_spending",
                        lambda fid, offset=0: seen.append(offset) or real(fid, today=_WED, offset=offset))
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = "22222222-2222-2222-2222-222222222222"
        sess["family_id"] = _FAM
    res = c.get("/api/week?offset=1")
    assert res.status_code == 200 and ">שבוע שעבר</h2>" in res.get_data(as_text=True)
    assert seen == [1]
    for bad in ("-1", "abc", "5000"):
        assert c.get(f"/api/week?offset={bad}").status_code == 422, bad


def test_a_sideways_swipe_locks_the_page_and_a_scroll_does_not():
    """מתן (2.10): "שאם אני גולל שם, זה לא יגלול לי את המסך למעלה ולמטה".
    הכיוון נקבע פעם אחת אחרי 8px; הצידה — ‎preventDefault‎ (לכן ‎passive: false‎).
    בדפדפן: נבדק עם תנועה אלכסונית, אנכית וקצרה."""
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "frontend/static/js/core.js").read_text(encoding="utf-8")
    part = js[js.index("let sx = null, sy = 0, axis = null, drag = null;"):]
    move = part[part.index("document.addEventListener('touchmove'"):]
    move = move[:move.index("}, { passive: false });")]
    assert "axis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y';" in move
    assert "if (axis !== 'x') return;" in move and "e.preventDefault();" in move
    assert move.index("if (axis !== 'x') return;") < move.index("e.preventDefault();"), "גלילה רגילה נחסמת"
