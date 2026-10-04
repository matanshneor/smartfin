"""שם ואייקון של קטגוריה נבדקים בשרת, לא רק במסך.

למסך יש ‎maxlength‎, לשרת לא היה כלום: בן משפחה שפונה ל-API ישירות יכול
היה לשמור אייקון כמו ‎<style>…</style>‎, והוא נכנס ל-‎innerHTML‎ של שורת
הביניים בדף הבית אצל כל המשפחה. ו-‎{"name": 5}‎ הפיל את המסלול ב-500.
"""
import pytest

from backend import supabase_config as db
from backend.app import app, limiter

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"
_ME  = "22222222-2222-2222-2222-222222222222"

# ארבעת המסלולים שכותבים שם ואייקון
_ROUTES = [
    ("post", "/api/categories",                  {"type": "expense"}),
    ("put",  "/api/categories/c1",               {}),
    ("post", "/api/projects/p1/categories",      {"type": "expense"}),
    ("put",  "/api/projects/p1/categories/c1",   {}),
]


@pytest.fixture
def client(monkeypatch):
    limiter.reset()
    app.config["TESTING"] = True
    wrote = []
    def fake(name):
        def write(*a, **k):
            wrote.append(name)
            return ({"id": "c1"}, None) if name.startswith("add") else True
        return write
    for fn in ("add_custom_category", "update_category",
               "add_project_category", "update_project_category"):
        monkeypatch.setattr(db, fn, fake(fn))
    monkeypatch.setattr(db, "get_project_for_transaction",
                        lambda pid, fid: {"id": pid, "owner_id": None})
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = _ME
            sess["family_id"] = _FAM
        yield c, wrote


@pytest.mark.parametrize("method,url,extra", _ROUTES, ids=[r[1] + ":" + r[0] for r in _ROUTES])
@pytest.mark.parametrize("fields", [
    {"name": "סופר", "icon": "<style>body{display:none}</style>"},
    # קצר מספיק כדי לעבור את מגבלת האורך — נתפס רק על התווים עצמם
    {"name": "סופר", "icon": "<img>"},
    {"name": "סופר", "icon": "🛒" * 20},
    {"name": "x" * 31, "icon": "🛒"},
    {"name": 5, "icon": "🛒"},
    {"name": "סופר", "icon": ["🛒"]},
], ids=["html-icon", "short-html-icon", "long-icon", "long-name", "number-name", "list-icon"])
def test_bad_fields_are_refused_before_anything_is_written(client, method, url, extra, fields):
    c, wrote = client

    res = getattr(c, method)(url, json={**extra, **fields})

    assert res.status_code == 422
    assert wrote == []


@pytest.mark.parametrize("method,url,extra", _ROUTES, ids=[r[1] + ":" + r[0] for r in _ROUTES])
@pytest.mark.parametrize("icon", ["🛒", "👨‍👩‍👧‍👦", "🇮🇱", ""])
def test_real_emoji_still_pass(client, method, url, extra, icon):
    """בקרת-נגד: אימוג'י מורכב (משפחה, דגל) ארוך מתו אחד — ועדיין אייקון."""
    c, wrote = client

    res = getattr(c, method)(url, json={**extra, "name": "סופר", "icon": icon})

    assert res.status_code in (200, 201), res.get_json()
    assert len(wrote) == 1
