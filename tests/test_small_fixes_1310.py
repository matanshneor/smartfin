"""תיקונים קטנים מהיומנים (מתן, 13.10)."""
import json
import re

import pytest

from backend import app as app_module
from backend import supabase_config as db
from backend.app import app

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"
_ME  = "22222222-2222-2222-2222-222222222222"


@pytest.mark.parametrize("path", ["/favicon.ico", "/apple-touch-icon.png",
                                  "/apple-touch-icon-precomposed.png"])
def test_the_icon_is_where_whatsapp_and_the_iphone_look_for_it(path):
    """בלעדיהם קישור לאפליקציה הופיע בלי הלוגו (‎404‎ ביומנים)."""
    res = app.test_client().get(path)

    assert res.status_code == 200
    assert res.mimetype == "image/png"


def test_robots_closes_only_the_api_and_the_receipts():
    body = app.test_client().get("/robots.txt").get_data(as_text=True)

    assert "Disallow: /api/" in body and "Disallow: /receipts/" in body
    # דף הנחיתה וקישורי ההזמנה צריכים תצוגה מקדימה בשיתוף
    assert "Disallow: /\n" not in body


def _page_data(html):
    raw = re.search(r'<script type="application/json" id="sf-page-data">(.*?)</script>', html, re.S)
    return json.loads(raw.group(1))


def test_the_add_window_lists_come_with_the_page(monkeypatch):
    """בלי שתי בקשות נוספות בכל עמוד — מה שהעמוד כבר שלף."""
    app.config["TESTING"] = True
    monkeypatch.setattr(db, "set_auth_token", lambda t: None)
    monkeypatch.setattr(db, "materialize_recurring", lambda fid: (0, True))
    monkeypatch.setattr(app_module, "family_settings", lambda: dict(db.DEFAULT_FAMILY_SETTINGS))
    cats = [{"id": "c1", "name": "סופר", "type": "expense", "icon": "🛒"}]
    monkeypatch.setattr(db, "fetch_home_page", lambda *a, **k: {
        "family": {"id": _FAM}, "settings": dict(db.DEFAULT_FAMILY_SETTINGS),
        "members": [{"id": _ME, "name": "מתן", "full_name": "מתן שניאור", "email": "secret@x.com"}],
        "categories": cats, "rows": [], "summary": db.summary_from_rows([]), "recent": [],
        "week": None, "is_new": False})
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = _ME
            sess["family_id"] = _FAM
        data = _page_data(c.get("/").get_data(as_text=True))

    assert data["lists"]["categories"] == cats
    # כמו ‎/api/family/members‎: מזהה ושם בלבד — לא מייל
    assert data["lists"]["members"] == [{"id": _ME, "name": "מתן"}]


def test_nothing_is_fetched_just_for_the_lists(monkeypatch):
    """עמוד שלא שלף קטגוריות — לא שולפים בשבילו; החלון יבקש כרגיל."""
    with app.test_request_context("/"):
        from flask import session
        session["family_id"] = _FAM
        monkeypatch.setattr(db, "_fetch_categories", lambda *a: pytest.fail("שליפה"))
        lists = app_module._client_lists()["client_lists"]()
    assert lists == {}


def test_the_js_takes_them_from_the_page():
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "frontend/static/js/transactions.js").read_text(encoding="utf-8")
    assert "if (Array.isArray(pageLists.categories)) categoriesCache = pageLists.categories;" in js
    assert "if (Array.isArray(pageLists.members)) membersCache = pageLists.members;" in js
