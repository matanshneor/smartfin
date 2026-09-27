"""‎max_rows = 1000‎: המסד מחזיר עד אלף שורות לבקשה — בלי שגיאה ובלי סימן.

שלושה מקומות ביקשו יותר ממה שיכול להגיע:
· הייצוא "המלא" — משפחה עם 55 עסקאות בחודש עוברת את זה בתוך שנה וחצי,
  ומאז הקובץ מכיל רק את האלף החדשות וייראה שלם.
· מנוע העסקאות הקבועות — רשימת המופעים הקיימים. מעבר לאלף הוא מפסיק
  לראות חלק מהם ויוצר אותם שוב.
· גרף המגמה — 12 חודשים של עסקאות. הוא מחושב עכשיו מטבלת הארכיון,
  שמקובצת ב-SQL (שורה לחודש), כך שהשניים מסכימים מעצם הבנייה.
"""
from datetime import date

import pytest

from backend import clock
from backend import supabase_config as db
from tests._fake_db import FakeSupabase

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"


def _rows(n, **extra):
    return [{"id": f"t{i:05d}", "family_id": _FAM, "amount": 1.0, "type": "expense",
             "date": f"20{10 + i // 400}-01-01", "project_id": None, **extra}
            for i in range(n)]


def test_the_full_export_is_actually_full(monkeypatch):
    fake = FakeSupabase(max_rows=1000, transactions=_rows(1005))
    monkeypatch.setattr(db, "get_client", lambda: fake)
    for name, value in [("get_projects", []), ("get_profile", {}), ("get_family", {}),
                        ("get_family_members", []), ("get_categories", [])]:
        monkeypatch.setattr(db, name, lambda *a, _v=value: _v)

    exported = db.export_account_data(_FAM, "me")["transactions"]

    assert len(exported) == 1005, f"הייצוא נחתך ב-{len(exported)}"
    assert len({t["id"] for t in exported}) == 1005, "עמודים חופפים — שורות כפולות"


def test_the_engine_sees_every_existing_occurrence(monkeypatch):
    """הרשימה של המופעים הקיימים היא של כל המשפחה, לא של סדרה אחת.
    שלוש סדרות שבועיות, 400 מופעים כל אחת — 1,200 ביחד. לכל אחת חסר
    בדיוק המופע של השבוע: ייווצרו שלושה, לא מאתיים."""
    import datetime as _dt
    start = _dt.date(2019, 1, 1)
    rows = []
    for t in ("a", "b", "c"):
        rows.append({"id": t, "family_id": _FAM, "amount": 10.0, "type": "expense",
                     "date": start.isoformat(), "description": "", "category_id": None,
                     "user_id": None, "is_recurring": True, "recurring_frequency": "weekly",
                     "recurring_end_date": None, "recurring_skips": None})
        rows += [{"id": f"{t}{k}", "family_id": _FAM, "recurring_parent_id": t,
                  "is_recurring": False,
                  "date": (start + _dt.timedelta(weeks=k)).isoformat()} for k in range(1, 401)]
    monkeypatch.setattr(clock, "today", lambda: start + _dt.timedelta(weeks=401))
    fake = FakeSupabase(max_rows=1000, transactions=rows)
    monkeypatch.setattr(db, "get_client", lambda: fake)
    monkeypatch.setattr(db, "get_categories", lambda fid: [])

    created, ok = db.materialize_recurring(_FAM)

    assert ok
    assert created == 3, f"נוצרו {created} — המנוע לא ראה את כל המופעים הקיימים"


# ─── גרף המגמה ───────────────────────────────────────────────────────────────

_ARCHIVE = [  # מהחדש לישן, כמו ש-get_months_archive מחזירה
    {"year": 2026, "month": 11, "income": 0, "expense": 999, "savings": 0, "balance": -999},
    {"year": 2026, "month": 9, "income": 10000, "expense": 6200.5, "savings": 500, "balance": 3799.5},
    {"year": 2026, "month": 8, "income": 9000, "expense": 7000, "savings": 0, "balance": 2000},
    {"year": 2025, "month": 10, "income": 1, "expense": 1, "savings": 1, "balance": 0},
    {"year": 2025, "month": 9, "income": 1, "expense": 1, "savings": 1, "balance": 0},
    {"year": 2025, "month": 8, "income": 1, "expense": 1, "savings": 1, "balance": 0},
]


def test_the_trend_is_the_archive_itself():
    """אותם מספרים בדיוק כמו בטבלה — כולל שכר הדירה של ה-30 בחודש הנוכחי,
    שהגרף הישן השמיט (הוא עצר ב"היום") והטבלה לא."""
    trend = db.monthly_trend(_ARCHIVE, 12, today=date(2026, 9, 16))

    by_key = {m["key"]: m for m in trend}
    assert by_key["2026-09"]["expense"] == 6200.5
    assert by_key["2026-08"]["income"] == 9000
    assert by_key["2026-09"]["month_name"] == "ספטמבר"


def test_the_trend_shows_no_future_months():
    """תשלום ששולם מראש לנובמבר לא יוצר עמודה ב"12 החודשים האחרונים"."""
    keys = [m["key"] for m in db.monthly_trend(_ARCHIVE, 12, today=date(2026, 9, 16))]

    assert "2026-11" not in keys


def test_the_trend_window_is_twelve_months_oldest_first():
    """אוקטובר 2025 עד ספטמבר 2026: אוקטובר על הגבול נכנס, ספטמבר 2025 לא."""
    keys = [m["key"] for m in db.monthly_trend(_ARCHIVE, 12, today=date(2026, 9, 16))]

    assert keys == ["2025-10", "2026-08", "2026-09"], keys
