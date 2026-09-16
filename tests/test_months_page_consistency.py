"""
בדיקות לעקביות עמוד ההשוואה בין חודשים.

עסקה המשויכת לפרויקט (טיול, שיפוץ) היא הוצאה חד-פעמית שמעוותת את תמונת
ה"חודש הרגיל", ולכן היא מוחרגת במכוון מכל מאזן חודשי באפליקציה — זו
החלטה מתועדת במיגרציה 20260804140000.

עמוד /months מציג שני דברים על אותם חודשים: גרף עמודות למעלה וטבלת
ארכיון מתחת. הטבלה תוקנה להחריג פרויקטים; הגרף נשכח. אותו יולי הופיע
כ-₪31,400 בגרף וכ-₪9,400 בטבלה, במרחק שני סנטימטרים, בלי שום הסבר —
זה נראה פשוט כמו אפליקציה שמחשבת לא נכון.
"""
import inspect
import re

import pytest

from backend import supabase_config as db

pytestmark = pytest.mark.unit

_PROJECT_FILTER = '.is_("project_id", "null")'


class _RecordingClient:
    """מתעד אילו פילטרים הופעלו על השאילתה."""

    def __init__(self, rows=None):
        self.filters = []
        self._rows = rows or []

    def table(self, _n):        return self
    def select(self, *a, **k):  return self
    def eq(self, *a, **k):      self.filters.append(("eq", a)); return self
    def gte(self, *a, **k):     return self
    def lt(self, *a, **k):      return self
    def is_(self, *a, **k):     self.filters.append(("is_", a)); return self
    def execute(self):          return self

    @property
    def not_(self):             return self
    @property
    def data(self):             return self._rows


def test_the_trend_chart_excludes_project_transactions(monkeypatch):
    """הלב: הגרף חייב לשאול את אותה שאלה כמו הטבלה שמתחתיו."""
    client = _RecordingClient()
    monkeypatch.setattr(db, "get_client", lambda: client)

    db.get_monthly_trend("fam-1", num_months=12)

    assert ("is_", ("project_id", "null")) in client.filters, (
        "גרף המגמה סופר עסקאות של פרויקטים, והטבלה מתחתיו לא — "
        "אותו חודש יוצג בשני מספרים שונים"
    )


def test_the_trend_and_the_monthly_summary_agree_on_the_rule():
    """שתי הפונקציות שמזינות את אותו עמוד חייבות להסכים. השוואת מקור
    ולא תוצאה, כי זו בדיוק הסתירה שנוצרת כשמתקנים אחת ושוכחים את השנייה."""
    trend   = inspect.getsource(db.get_monthly_trend)
    summary = inspect.getsource(db.get_monthly_summary)

    assert (_PROJECT_FILTER in trend) == (_PROJECT_FILTER in summary), (
        "get_monthly_trend ו-get_monthly_summary לא מסכימות על החרגת פרויקטים"
    )


def test_the_archive_function_also_excludes_them():
    """הצד השלישי של אותו עמוד יושב ב-SQL ולא בפייתון, ולכן נבדק בנפרד —
    אחרת 'כולם מסכימים' יכול להיות נכון רק על שתיים מתוך שלוש."""
    from pathlib import Path
    sql = (Path(__file__).resolve().parent.parent
           / "backend/supabase/migrations"
           / "20260804140000_months_archive_exclude_projects.sql").read_text(encoding="utf-8")

    assert re.search(r"project_id\s+IS\s+NULL", sql, re.IGNORECASE)


def test_transactions_are_still_counted_when_they_have_no_project(monkeypatch):
    """בקרת-נגד: ההחרגה לא אמורה לרוקן את הגרף מעסקאות רגילות."""
    rows = [
        {"type": "expense", "amount": 100, "date": "2026-09-03"},
        {"type": "income",  "amount": 500, "date": "2026-09-05"},
    ]
    monkeypatch.setattr(db, "get_client", lambda: _RecordingClient(rows))

    trend = db.get_monthly_trend("fam-1", num_months=3)

    september = [m for m in trend if m.get("month") == 9]
    assert september, f"החודש נעלם מהגרף: {trend}"
    assert september[0]["expense"] == 100
    assert september[0]["income"] == 500
