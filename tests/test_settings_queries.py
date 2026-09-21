"""
בדיקות לשליפות של עמוד ההגדרות.

שני דברים באותו עמוד:

‎_project_totals‎ משכה את *כל* עסקאות הפרויקטים של המשפחה, מאז ומתמיד,
בכל טעינה — וחיברה אותן בפייתון. אצל משפחה עם טיול אחד זה כבר 56 שורות
שנמשכות כדי לקבל מספר אחד, והמספר גדל לנצח.

והפרופיל של המשתמש נשלף פעמיים: פעם ברשימת חברי המשפחה, שמחזירה שם
מלא, אימייל, טלפון ומקום עבודה לכל חבר — ופעם נוספת בנפרד.
"""
import inspect
from pathlib import Path

import pytest

from backend import app as app_module
from backend import supabase_config as db
from backend.app import app

pytestmark = pytest.mark.unit

_ME  = "11111111-1111-1111-1111-111111111111"
_FAM = "22222222-2222-2222-2222-222222222222"


# ─── הסכומים מחושבים במסד ────────────────────────────────────────────────────

def test_project_totals_does_not_fetch_every_transaction():
    src = inspect.getsource(db._project_totals)

    assert 'rpc("project_totals"' in src
    assert "select(" not in src, "עדיין מושך שורות ומחבר בפייתון"


def test_it_still_returns_the_same_shape(monkeypatch):
    """בקרת-נגד: הקוראים מצפים ל-‎{id: {expense, income, savings}}‎."""
    class _Fake:
        def rpc(self, name, params): return self
        def execute(self):
            self.data = [{"project_id": "p1", "expense": "500.5",
                          "income": None, "savings": 0}]
            return self

    monkeypatch.setattr(db, "get_client", lambda: _Fake())

    assert db._project_totals(_FAM) == {
        "p1": {"expense": 500.5, "income": 0.0, "savings": 0.0}}


def test_the_rpc_keeps_row_level_security():
    """‎security invoker‎ ולא definer: אין שום סיבה לעקוף RLS כאן, וזה
    היה פותח דלת לסכומים של משפחה אחרת."""
    sql = (Path(__file__).resolve().parent.parent
           / "backend/supabase/migrations/20260916130000_project_totals.sql"
           ).read_text(encoding="utf-8")

    assert "security invoker" in sql
    assert "security definer" not in sql
    assert "revoke all" in sql and "anon" in sql


# ─── הפרופיל נשלף פעם אחת ────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    calls = []
    monkeypatch.setattr(app_module.db, "get_profile",
                        lambda uid: (calls.append(uid) or {"name": "מתן שניאור"}))
    monkeypatch.setattr(app_module.db, "get_family_members",
                        lambda fid: [{"id": _ME, "name": "מתן", "full_name": "מתן שניאור",
                                      "email": "m@x.com", "phone": "050", "workplace": "עבודה"}])
    for fn, val in (("get_categories", []), ("get_family", {}),
                    ("get_recurring_transactions", []), ("get_projects", []),
                    # ספירת העסקאות שמוצגת באישור איפוס החשבון
                    ("family_transaction_count", 0)):
        monkeypatch.setattr(app_module.db, fn, lambda *a, _v=val, **k: _v)
    monkeypatch.setattr(app_module, "family_settings",
                        lambda: dict(db.DEFAULT_FAMILY_SETTINGS))
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]   = _ME
            sess["family_id"] = _FAM
        yield c, calls


def test_the_settings_page_does_not_fetch_the_profile_twice(client):
    c, calls = client

    c.get("/settings")

    assert calls == [], "הפרופיל נשלף שוב למרות שהוא ברשימת החברים"


def test_the_details_shown_are_still_the_right_ones(client):
    """בקרת-נגד: אופטימיזציה שמציגה שם ריק גרועה מפנייה מיותרת."""
    c, _ = client

    body = c.get("/settings").get_data(as_text=True)

    assert "מתן שניאור" in body


def test_it_falls_back_when_the_member_list_cannot_help(client, monkeypatch):
    """חשבון בלי משפחה, או חבר שלא חזר מהרשימה — עדיין צריך את הפרטים."""
    c, calls = client
    monkeypatch.setattr(app_module.db, "get_family_members", lambda fid: [])

    c.get("/settings")

    assert calls == [_ME], "אין נפילה חזרה — המשתמש יראה מסך בלי הפרטים שלו"
