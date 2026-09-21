"""
בדיקות להשלמת המופעים עצמה — materialize_recurring, ולא רק מחולל
התאריכים שכבר מכוסה ב-test_recurring.py.

הבאג: הדדופ זיהה מופע קיים לפי צמד (תבנית, תאריך מדויק). שינוי תאריך
בתבנית — למשל משכורת שעוברת מה-5 ל-10 לחודש — מייצר סדרת תאריכים חדשה
שאף אחד ממנה לא מוכר, ולכן **כל החודשים אחורה נוצרו מחדש**. משכורת של
₪14,000 הוכפלה על שמונה חודשים בבת אחת, בדשבורד, בעמוד החודש ובגרף
ההשוואה, בלי שהמשתמש עשה שום דבר חוץ מלתקן תאריך.

האינדקס הייחודי במסד לא עוזר כאן: הוא מפתחו על (תבנית, תאריך), והתאריכים
באמת שונים.

הכלל שנבדק: מופע אחד לכל תבנית לכל תקופה — חודש קלנדרי בתדירות חודשית.
"""
from datetime import date

import pytest

from backend import clock
from backend import supabase_config as db

pytestmark = pytest.mark.unit


class _FakeClient:
    """לקוח Supabase מינימלי: מחזיר תבניות ומופעים קיימים, ואוסף מה שנכתב."""

    def __init__(self, templates, instances):
        self._templates = templates
        self._instances = instances
        self.inserted = []
        self._select = None

    def table(self, _name):            return self
    def select(self, cols, **k):       self._select = cols; return self
    def eq(self, *a, **k):             return self
    def execute(self):                 return self
    def insert(self, rows, **k):       self.inserted.extend(rows); return self

    @property
    def not_(self):                    return self
    def is_(self, *a, **k):            return self

    @property
    def data(self):
        if self._select == "*":
            return self._templates
        return [{"recurring_parent_id": p, "date": d} for p, d in self._instances]


_TEMPLATE_ID = "11111111-1111-1111-1111-111111111111"


def _salary(day, freq="monthly_same"):
    return {
        "id": _TEMPLATE_ID, "amount": 14000, "type": "income",
        "date": f"2026-01-{day:02d}", "description": "משכורת",
        "category_id": None, "user_id": None,
        "recurring_frequency": freq, "recurring_end_date": None,
    }


@pytest.fixture
def frozen_september(monkeypatch):
    """מקפיא את 'היום' על 16/09/2026, כדי שהבדיקות לא ישתנו עם הזמן.

    הגרסה הקודמת דרסה את ‎datetime.date.today‎ — ומנוע העסקאות הקבועות
    לא קורא לו בכלל, אלא ל-‎clock.today()‎, שנגזר מ-‎datetime.now(ISRAEL)‎.
    כלומר הזמן מעולם לא הוקפא, והבדיקות רצו מול התאריך האמיתי.

    זה לא נשאר תיאורטי: הבדיקה השבועית נשענת על כך שלא חלף שבוע נוסף
    מאז 15/09, ולכן היא עברה במשך שישה ימים ונפלה ב-CI ב-22/09 — יום
    אחרי שנכתבה שורת הקוד שנבדקה, ובלי שום קשר אליה."""
    import datetime as _dt
    monkeypatch.setattr(clock, "today", lambda: _dt.date(2026, 9, 16))
    monkeypatch.setattr(clock, "now", lambda: _dt.datetime(2026, 9, 16, 12, 0))
    yield


def _run(monkeypatch, templates, instances):
    client = _FakeClient(templates, instances)
    monkeypatch.setattr(db, "get_client", lambda: client)
    monkeypatch.setattr(db, "get_categories", lambda fid: [])
    # ‎(created, ok)‎ — הדגל השני נוסף כדי שכישלון לא ייראה כהצלחה
    # ויסמן "סונכרן להיום" (ראו tests/test_recurring_sync.py)
    created, ok = db.materialize_recurring("fam-1")
    assert ok, "הריצה נכשלה — הבדיקה שלמטה תבדוק את הדבר הלא נכון"
    return created, client.inserted


# ─── הבאג עצמו ───────────────────────────────────────────────────────────────

def test_moving_a_monthly_template_does_not_duplicate_past_months(
        frozen_september, monkeypatch):
    """הלב. המשכורת שולמה ב-5 לחודש מפברואר עד ספטמבר; המשתמש מתקן את
    התבנית ל-10. אסור שייווצר ולו מופע אחד — כל חודש כבר קיבל את שלו."""
    already = [(_TEMPLATE_ID, f"2026-{m:02d}-05") for m in range(2, 10)]

    created, rows = _run(monkeypatch, [_salary(10)], already)

    assert created == 0, (
        f"נוצרו {created} מופעים אחרי שינוי תאריך — "
        f"הכנסות {len(already)} חודשים הוכפלו: {[r['date'] for r in rows]}"
    )


def test_switching_to_a_fixed_day_of_month_does_not_duplicate_either(
        frozen_september, monkeypatch):
    """אותו באג דרך שינוי תדירות ולא תאריך: monthly_same ← monthly_15."""
    already = [(_TEMPLATE_ID, f"2026-{m:02d}-05") for m in range(2, 10)]

    created, _ = _run(monkeypatch, [_salary(5, freq="monthly_15")], already)

    assert created == 0


# ─── בקרות-נגד: הזהירות לא מבטלת את התכונה ───────────────────────────────────

def test_a_brand_new_template_still_fills_in_every_month(
        frozen_september, monkeypatch):
    """בלי זה ה'תיקון' היה פשוט מכבה את העסקאות הקבועות."""
    created, rows = _run(monkeypatch, [_salary(5)], [])

    assert created == 8, f"נוצרו {created} במקום פברואר–ספטמבר"
    assert [r["date"] for r in rows][0] == "2026-02-05"
    assert all(r["recurring_parent_id"] == _TEMPLATE_ID for r in rows)


def test_a_month_that_is_genuinely_missing_is_still_filled(
        frozen_september, monkeypatch):
    """מופע שנמחק ידנית — החודש שלו ריק, ולכן הוא חוזר."""
    already = [(_TEMPLATE_ID, f"2026-{m:02d}-05") for m in range(2, 10) if m != 5]

    created, rows = _run(monkeypatch, [_salary(5)], already)

    assert created == 1
    assert rows[0]["date"].startswith("2026-05")


def test_two_templates_do_not_block_each_other(frozen_september, monkeypatch):
    """התקופה נספרת לכל תבנית בנפרד — שכר דירה ומשכורת באותו חודש."""
    rent = dict(_salary(5), id="22222222-2222-2222-2222-222222222222",
                type="expense", description="שכר דירה")
    already = [(_TEMPLATE_ID, f"2026-{m:02d}-05") for m in range(2, 10)]

    created, rows = _run(monkeypatch, [_salary(5), rent], already)

    assert created == 8
    assert {r["recurring_parent_id"] for r in rows} == {rent["id"]}


def test_weekly_templates_use_proximity_not_the_calendar_month(
        frozen_september, monkeypatch):
    """לשבועית אין 'חודש' כתקופה — מופע שזז ביום-יומיים הוא אותו מופע,
    אבל השבוע הבא הוא מופע חדש ולגיטימי."""
    weekly = dict(_salary(5), date="2026-09-01", recurring_frequency="weekly")
    already = [(_TEMPLATE_ID, "2026-09-08"), (_TEMPLATE_ID, "2026-09-15")]

    created, rows = _run(monkeypatch, [weekly], already)

    assert created == 0, f"מופעים שבועיים קיימים נוצרו שוב: {[r['date'] for r in rows]}"
