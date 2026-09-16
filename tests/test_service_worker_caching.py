"""
בדיקות למה שה-Service Worker שומר במטמון.

הוא הגיש עמודים שמורים כשהרשת חלשה. זה נכון לעמוד תוכן — ולא לעמוד
שמציג כסף. משתמש בחיבור סלולרי גרוע קיבל מסך מלא ומעוצב עם
"נשאר בעו״ש ₪1,270" מהביקור הקודם, אולי מלפני ימים. אנימציית הספירה
אפילו רצה עליהם, אז הם נראו טריים. שום דבר לא סימן שזה ישן.

הודעה ברורה שאין חיבור טובה ממספר שקרי — במיוחד כשמישהו עלול לקבל
החלטה כספית על סמך המסך הזה.

בדיקות על תוכן הקובץ: אין כאן סביבת Service Worker להריץ בה.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SW = (Path(__file__).resolve().parent.parent
       / "frontend/static/sw.js").read_text(encoding="utf-8")


def _cacheable():
    m = re.search(r"CACHEABLE_PAGES\s*=\s*\[([^\]]*)\]", _SW)
    assert m, "לא נמצאה רשימת העמודים הניתנים לשמירה"
    return set(re.findall(r"'([^']+)'", m.group(1)))


# ─── מה לא נשמר ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("page,what", [
    ("/",          "יתרה ועסקאות אחרונות"),
    ("/month",     "כל מספרי החודש והגרפים"),
    ("/months",    "היסטוריה חודשית"),
    ("/projects",  "סכומי פרויקטים"),
    ("/settings",  "קוד הזמנה, טלפון ומקום עבודה"),
    ("/login",     "המייל השמור בטופס"),
])
def test_pages_with_money_or_personal_data_are_never_served_from_cache(page, what):
    assert page not in _cacheable(), f"{page} נשמר במטמון — {what}"


def test_only_the_legal_pages_are_cacheable():
    """הם זהים לכל המשתמשים ולא משתנים. כל השאר — לא."""
    assert _cacheable() == {"/privacy", "/terms"}


def test_api_calls_are_still_never_intercepted():
    """בקרת-נגד: נתוני עסקאות משתנים כל הזמן, והגשה שקטה של תשובה ישנה
    גרועה משגיאת רשת ברורה."""
    assert "url.pathname.startsWith('/api/')" in _SW


def test_static_assets_are_still_cached():
    """בקרת-נגד: בלי זה כל טעינה מורידה מחדש 99KB CSS ו-77KB JS."""
    assert "url.pathname.startsWith('/static/')" in _SW
    assert "stale-while-revalidate" in _SW or "cache.put(e.request, res.clone())" in _SW


# ─── מה מוצג במקום ───────────────────────────────────────────────────────────

def test_there_is_an_offline_page_and_it_says_why_there_are_no_numbers():
    """"אין חיבור" לבד משאיר את המשתמש לתהות אם הנתונים שלו אבדו."""
    assert "function offlinePage()" in _SW
    assert "אין חיבור לאינטרנט" in _SW
    assert "לא מוצגים כאן נתונים ישנים" in _SW


def test_the_offline_page_offers_a_way_forward():
    """באפליקציה מותקנת בטלפון אין כפתור רענון על המסך, אז בלי כפתור
    הדרך היחידה קדימה היא לנחש."""
    assert "location.reload()" in _SW


def test_the_offline_page_looks_like_the_app():
    """גיליון הסגנון כבר במטמון, אז זה בחינם — וההבדל הוא בין מסך של
    האפליקציה לבין שגיאת דפדפן גולמית."""
    assert "/static/css/style.css" in _SW


def test_the_installed_app_gets_our_offline_page_not_the_browsers():
    """‎start_url‎ במניפסט הוא ‎/‎. כשהוא לא עבר דרך ה-Service Worker,
    פתיחת האפליקציה בלי רשת הציגה את מסך השגיאה של הדפדפן."""
    import json
    manifest = json.loads((Path(__file__).resolve().parent.parent
                           / "frontend/static/manifest.json").read_text(encoding="utf-8"))

    assert manifest["start_url"] == "/"
    assert "/" not in _cacheable()
    # ‎/‎ נופל למסלול ה-fetch-with-fallback ולא ל-return מוקדם
    assert "e.respondWith(fetch(e.request).catch(() => offlinePage()));" in _SW


def test_the_cache_version_was_bumped():
    """בלי זה משתמשים קיימים ממשיכים לקבל את העמודים הישנים שכבר שמורים
    אצלם, והתיקון לא מגיע לאף אחד מהם."""
    assert "smartfin-v14" in _SW


def test_chart_js_is_not_downloaded_by_everyone_on_install():
    """70KB דחוסים — הקובץ הכבד באפליקציה, יותר משלושה מונים מכל ה-CSS —
    שנדרש רק בשלושה עמודים. הוא נכנס למטמון לבד בשימוש הראשון."""
    block = _SW[_SW.index("const PRECACHE"):_SW.index("];", _SW.index("const PRECACHE"))]
    # בלי ההערות: השם מופיע שם בהסבר למה הוא *לא* ברשימה, ובדיקה
    # שנופלת על הסבר היא בדיקה שמישהו ימחק במקום לתקן
    precache = re.sub(r"^\s*//.*$", "", block, flags=re.M)

    assert "chart.umd" not in precache
    assert "/static/css/style.css" in precache, "הטעינה-מראש התרוקנה לגמרי"
