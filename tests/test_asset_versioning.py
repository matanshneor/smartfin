"""
בדיקות לחתימת הנכסים הסטטיים.

כל קובץ נשלח עם "no-cache", כלומר הדפדפן שאל את השרת בכל טעינת עמוד אם
העותק שלו עדיין תקף. שש שאלות בכל עמוד, כולן נענות "לא השתנה", וכל אחת
תופסת אחד משני ה-workers — שש מתוך שבע הפניות בטעינה רגילה הן שיחה על
כלום.

הסיכון בתיקון גדול מהבעיה: כתובת שנשמרת לשנה והחתימה שלה לא משתנה היא
קובץ ישן שאין שום דרך לרענן מרחוק — לא ברענון, לא בניקוי, רק להמתין שנה.
לכן החתימה נגזרת מתוכן הקובץ ולא ממספר ידני, והבדיקה המרכזית כאן היא
שהיא באמת משתנה כשהתוכן משתנה.
"""
import re
from pathlib import Path

import pytest

from backend import app as app_module
from backend.app import app

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _fresh_hashes():
    app_module._ASSET_HASHES.clear()
    yield
    app_module._ASSET_HASHES.clear()


def _rendered(filename="css/style.css"):
    from flask import render_template_string
    with app.test_request_context("/"):
        return render_template_string(
            "{{ url_for('static', filename='" + filename + "') }}")


# ─── הלב: החתימה עוקבת אחרי התוכן ────────────────────────────────────────────

def test_the_version_changes_when_the_file_changes(tmp_path, monkeypatch):
    """אם זה לא נכון, משתמשים מקבלים קובץ ישן במשך שנה ואין דרך לתקן."""
    static = tmp_path / "static"
    static.mkdir()
    asset = static / "x.css"
    monkeypatch.setattr(app, "static_folder", str(static))

    asset.write_text("body { color: red }", encoding="utf-8")
    before = app_module._asset_version("x.css")

    app_module._ASSET_HASHES.clear()
    asset.write_text("body { color: blue }", encoding="utf-8")
    after = app_module._asset_version("x.css")

    assert before and after
    assert before != after, "התוכן השתנה והחתימה לא — קובץ ישן יוגש לשנה"


def test_the_version_is_derived_from_content_not_a_manual_number():
    """מספר שצריך לזכור לעדכן הוא מספר שיישכח."""
    import inspect
    src = inspect.getsource(app_module._asset_version)

    assert "sha256" in src
    assert "read()" in src


def test_the_same_file_keeps_the_same_version():
    """בקרת-נגד: חתימה שמשתנה לחינם מבטלת את המטמון בכל פריסה."""
    assert _rendered() == _rendered()


# ─── הכתובות שנוצרות ─────────────────────────────────────────────────────────

def test_static_urls_carry_a_version():
    url = _rendered()

    assert re.search(r"/static/css/style\.css\?v=[0-9a-f]{8}$", url), url


def test_templates_did_not_need_to_change():
    """48 קריאות ל-url_for בתבניות. דריסה ולא פונקציה חדשה, כדי שגם
    קריאה שתיכתב מחר תקבל את זה בלי שאיש יזכור."""
    html = (_ROOT / "frontend/templates/base.html").read_text(encoding="utf-8")

    assert "url_for('static'" in html
    assert "?v=" not in html, "החתימה נכתבה ידנית בתבנית"


def test_a_missing_file_does_not_take_the_page_down():
    """נכס חסר הוא באג שצריך לראות, לא סיבה ל-500 על כל העמוד."""
    assert app_module._asset_version("does/not/exist.css") == ""
    assert _rendered("does/not/exist.css") == "/static/does/not/exist.css"


# ─── כותרות המטמון ───────────────────────────────────────────────────────────

def test_a_versioned_url_is_cached_for_a_year():
    app.config["TESTING"] = True
    headers = app.test_client().get("/static/css/style.css?v=abc123").headers

    assert "max-age=31536000" in headers["Cache-Control"]
    assert "immutable" in headers["Cache-Control"]


def test_an_unversioned_url_is_not():
    """זו ההגנה: כתובת בלי חתימה היא כתובת שאי אפשר לרענן, ולכן היא
    לא נשמרת לשנה. בלי התנאי הזה טעות אחת נועלת קובץ לשנה."""
    app.config["TESTING"] = True
    headers = app.test_client().get("/static/css/style.css").headers

    assert "max-age=31536000" not in headers.get("Cache-Control", "")


# ─── ה-Service Worker הותאם ──────────────────────────────────────────────────

def test_the_service_worker_does_not_precache_unversioned_urls():
    """רשימה קבועה לא יכולה לדעת את החתימה. היא הייתה מורידה כתובות
    שאף עמוד לא מבקש — הורדה כפולה, ומטמון שלא נוגעים בו."""
    sw = (_ROOT / "frontend/static/sw.js").read_text(encoding="utf-8")
    block = sw[sw.index("const PRECACHE"):sw.index("];", sw.index("const PRECACHE"))]

    assert "/static/" not in block


def test_the_service_worker_treats_versioned_assets_as_immutable():
    sw = (_ROOT / "frontend/static/sw.js").read_text(encoding="utf-8")

    assert "searchParams.has('v')" in sw
    assert "if (cached && immutable) return cached;" in sw
