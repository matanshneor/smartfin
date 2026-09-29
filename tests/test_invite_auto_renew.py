"""בהגדרות של המנהל תמיד יש קוד הזמנה תקף — בלי ללחוץ "קוד חדש".

בקשת מתן (29.9.2026). הקוד תקף שבוע, והקוד של המשפחה פג בשקט באותו
בוקר: מי שנכנס להגדרות כדי לשלוח קוד מצא "הקוד פג. הפיקו חדש".

קוד חדש נוצר רק כשהקודם **כבר פג** — כך אף הזמנה ששלחת ועדיין בתוקף לא
מתבטלת. "קוד חדש" נשאר, לביטול מיידי של קוד שדלף. ורק למנהל: החלפת קוד
היא הרשאה שלו, ובני משפחה אחרים רואים "פג" עד שהוא נכנס.
"""
from datetime import timedelta

import pytest

from backend import app as app_module
from backend import clock
from backend import supabase_config as db
from backend.app import app

pytestmark = pytest.mark.unit

_ME    = "11111111-1111-1111-1111-111111111111"
_OTHER = "33333333-3333-3333-3333-333333333333"
_FAM   = "22222222-2222-2222-2222-222222222222"


def _stamp(days):
    return (clock.now_utc() + timedelta(days=days)).isoformat()


@pytest.fixture
def settings_page(monkeypatch):
    app.config["TESTING"] = True
    state = {"family": None, "rotations": 0, "rotate_result": ("NEW777", None)}

    def rotate():
        state["rotations"] += 1
        code, err = state["rotate_result"]
        if code:
            state["family"] = {**state["family"], "invite_code": code,
                               "invite_code_expires_at": _stamp(7)}
        return code, err

    monkeypatch.setattr(app_module.db, "get_family", lambda fid: dict(state["family"]))
    monkeypatch.setattr(app_module.db, "rotate_invite_code", rotate)
    monkeypatch.setattr(app_module.db, "get_family_members",
                        lambda fid: [{"id": _ME, "name": "מתן", "full_name": "מתן"}])
    for fn, val in (("get_categories", []), ("get_recurring_transactions", []),
                    ("get_projects", []), ("family_transaction_count", 0)):
        monkeypatch.setattr(app_module.db, fn, lambda *a, _v=val, **k: _v)
    monkeypatch.setattr(app_module, "family_settings",
                        lambda: dict(db.DEFAULT_FAMILY_SETTINGS))

    def open_as(manager, code="OLD111", expires_in_days=-1):
        state["family"] = {"id": _FAM, "name": "שניאור", "manager_id": manager,
                           "invite_code": code, "invite_code_expires_at": _stamp(expires_in_days)}
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["user_id"] = _ME
                sess["family_id"] = _FAM
            return c.get("/settings").get_data(as_text=True)
    return state, open_as


def test_the_manager_gets_a_fresh_code_instead_of_an_expired_one(settings_page):
    state, open_as = settings_page

    html = open_as(manager=_ME, expires_in_days=-1)

    assert state["rotations"] == 1
    assert "NEW777" in html and "OLD111" not in html
    assert "הקוד פג" not in html


def test_a_code_that_is_still_valid_is_left_alone(settings_page):
    """אחרת כל כניסה להגדרות הייתה מבטלת הזמנה ששלחת אתמול."""
    state, open_as = settings_page

    html = open_as(manager=_ME, expires_in_days=3)

    assert state["rotations"] == 0
    assert "OLD111" in html


def test_a_member_who_is_not_the_manager_does_not_renew_it(settings_page):
    state, open_as = settings_page

    html = open_as(manager=_OTHER, expires_in_days=-1)

    assert state["rotations"] == 0
    assert "הקוד פג" in html


def test_a_failed_renewal_still_shows_the_page_and_says_it_expired(settings_page):
    state, open_as = settings_page
    state["rotate_result"] = (None, "db down")

    html = open_as(manager=_ME, expires_in_days=-1)

    assert state["rotations"] == 1
    assert "הקוד פג" in html
