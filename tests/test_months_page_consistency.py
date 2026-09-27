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


# גרף המגמה נשלף בנפרד עד 27.9.2026, ושלוש הבדיקות שישבו כאן בדקו
# שהשליפה שלו מחריגה פרויקטים כמו הטבלה. הוא נגזר עכשיו מהטבלה עצמה
# (‎db.monthly_trend(archive)‎), אז הסכמה ביניהם היא מבנית — ונבדקת
# בהתנהגות ב-tests/test_row_cap.py. מה שנשאר לבדוק כאן הוא המקור היחיד.


def test_the_archive_function_also_excludes_them():
    """הצד השלישי של אותו עמוד יושב ב-SQL ולא בפייתון, ולכן נבדק בנפרד —
    אחרת 'כולם מסכימים' יכול להיות נכון רק על שתיים מתוך שלוש."""
    from pathlib import Path
    sql = (Path(__file__).resolve().parent.parent
           / "backend/supabase/migrations"
           / "20260804140000_months_archive_exclude_projects.sql").read_text(encoding="utf-8")

    assert re.search(r"project_id\s+IS\s+NULL", sql, re.IGNORECASE)
