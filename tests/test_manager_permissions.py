"""
תפקיד "מנהל המשפחה" היה תג, לא הרשאה.

הוא נוסף כדי שמישהו יהיה אחראי, ונאכף על פעולה אחת בלבד — הסרת חבר.
כל השאר נשאר פתוח לכל מי שהצטרף עם קוד בן שישה תווים, ובראשו
‎/api/account/reset‎: ה-‎scope‎ שלו הוא "כל המשפחה" כברירת מחדל, אין
בדיקת מנהל, והאימות היחיד הוא הסיסמה של מי שקורא. כלומר חבר יחיד יכול
היה למחוק את היסטוריית הכסף של כל המשפחה.

ופער שני שיתק את התפקיד עצמו: ‎delete_my_account‎ נכתב חודשיים לפני
שנוסף ‎manager_id‎ ולא עודכן. מנהל שמחק את חשבונו הותיר את השדה ריק,
ומאז ‎remove_family_member‎ נכשל לתמיד — ‎NULL is distinct from <uuid>‎
תמיד אמת — ואין בשום מקום קוד שמציב מנהל מחדש.
"""
import pytest

from backend import app as app_module
from backend.app import app, limiter

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"
_ME  = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(autouse=True)
def _fresh_limits():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setattr(app_module.db, "sign_in",
                        lambda e, p: (type("R", (), {"session": type("S", (), {
                            "access_token": "t"})()})(), None))
    monkeypatch.setattr(app_module.db, "set_auth_token", lambda t: None)
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]    = _ME
            sess["family_id"]  = _FAM
            sess["user_email"] = "me@example.com"
        yield c


def _manager(monkeypatch, yes):
    monkeypatch.setattr(app_module.db, "is_family_manager", lambda: yes)


def _reset(client, scope="family"):
    return client.post("/api/account/reset", json={"password": "pw", "scope": scope})


# ─── איפוס עסקאות המשפחה ────────────────────────────────────────────────────

def test_a_plain_member_cannot_erase_the_family_history(client, monkeypatch):
    """הלב. עד היום זה עבד."""
    _manager(monkeypatch, False)
    monkeypatch.setattr(app_module.db, "reset_transactions",
                        lambda *a, **k: pytest.fail("היסטוריית המשפחה נמחקה בידי חבר רגיל"))

    res = _reset(client)

    assert res.status_code == 403
    assert "רק מנהל המשפחה" in res.get_json()["error"]


def test_the_manager_still_can(client, monkeypatch):
    """בקרת-נגד: התכונה עצמה חייבת להמשיך לעבוד."""
    _manager(monkeypatch, True)
    monkeypatch.setattr(app_module.db, "reset_transactions", lambda *a, **k: (12, None))

    res = _reset(client)

    assert res.status_code == 200
    assert res.get_json() == {"status": "ok", "deleted": 12}


def test_a_plain_member_can_still_erase_only_their_own(client, monkeypatch):
    """בקרת-נגד חשובה: זה הכסף של מי שמבקש, ואין סיבה לחסום אותו."""
    _manager(monkeypatch, lambda: pytest.fail("נבדקה הרשאת מנהל על 'רק שלי'"))
    monkeypatch.setattr(app_module.db, "is_family_manager",
                        lambda: pytest.fail("נבדקה הרשאת מנהל על 'רק שלי'"))
    seen = {}
    monkeypatch.setattr(app_module.db, "reset_transactions",
                        lambda fam, only_user_id=None: (seen.update(u=only_user_id) or (3, None)))

    assert _reset(client, scope="mine").status_code == 200
    assert seen["u"] == _ME


# ─── שתי הפעולות ההרסניות האחרות ────────────────────────────────────────────

def test_a_plain_member_cannot_delete_a_category(client, monkeypatch):
    _manager(monkeypatch, False)
    monkeypatch.setattr(app_module.db, "get_client",
                        lambda: pytest.fail("קטגוריה נמחקה בידי חבר רגיל"))

    assert client.delete("/api/categories/abc").status_code == 403


def test_a_plain_member_cannot_rotate_the_invite_code(client, monkeypatch):
    """החלפת הקוד פוסלת גם הזמנות שכבר נשלחו."""
    _manager(monkeypatch, False)
    monkeypatch.setattr(app_module.db, "rotate_invite_code",
                        lambda: pytest.fail("הקוד הוחלף בידי חבר רגיל"))

    assert client.post("/api/family/invite-code").status_code == 403


def test_the_manager_can_rotate_it(client, monkeypatch):
    _manager(monkeypatch, True)
    monkeypatch.setattr(app_module.db, "rotate_invite_code", lambda: ("ABC123", None))

    res = client.post("/api/family/invite-code")

    assert res.get_json() == {"status": "ok", "invite_code": "ABC123"}


# ─── מה שנשאר משותף ─────────────────────────────────────────────────────────

def test_budgets_and_settings_stay_shared(client, monkeypatch):
    """החלטה מפורשת: תקציבים, התראות ושם המשפחה הם החלטות שהמשפחה
    מקבלת יחד, ולא של המנהל."""
    monkeypatch.setattr(app_module.db, "is_family_manager",
                        lambda: pytest.fail("נדרשה הרשאת מנהל להגדרות משותפות"))
    monkeypatch.setattr(app_module.db, "update_family_settings", lambda *a, **k: True)
    monkeypatch.setattr(app_module.db, "get_family_settings",
                        lambda fid: dict(app_module.db.DEFAULT_FAMILY_SETTINGS))
    monkeypatch.setattr(app_module, "family_settings",
                        lambda: dict(app_module.db.DEFAULT_FAMILY_SETTINGS))

    res = client.put("/api/family/settings", json={"show_workplace": True})

    assert res.status_code == 200


# ─── "לא ידוע" אינו "כן" ────────────────────────────────────────────────────

def test_an_unverifiable_permission_is_refused(client, monkeypatch):
    def _boom():
        raise app_module.db.DataUnavailable("is_family_manager")
    monkeypatch.setattr(app_module.db, "is_family_manager", _boom)
    monkeypatch.setattr(app_module.db, "reset_transactions",
                        lambda *a, **k: pytest.fail("נמחק בלי לדעת מי מבקש"))

    assert _reset(client).status_code == 503


# ─── הכלל נאכף במסד, לא רק בהסתרת כפתור ─────────────────────────────────────

def _migration():
    from pathlib import Path
    return (Path(__file__).resolve().parent.parent
            / "backend/supabase/migrations/20260921210000_manager_only_destructive.sql"
            ).read_text(encoding="utf-8")


def test_the_check_is_derived_from_the_token_not_a_parameter():
    """פונקציה שמקבלת מזהה כפרמטר אפשר לשאול על מישהו אחר."""
    sql = _migration()
    body = sql[sql.index("create or replace function public.is_family_manager"):]
    body = body[:body.index("$$;")]

    assert "auth.uid()" in body
    assert "returns boolean" in body


def test_the_manager_role_is_handed_over_when_the_account_is_deleted():
    """אומת ב-rollback מול המסד החי: מנהל מחק את חשבונו, והניהול עבר
    לחבר שנשאר. בלי זה המשפחה לא יכולה להסיר חבר לעולם."""
    sql = _migration()
    body = sql[sql.index("create or replace function public.delete_my_account"):]

    assert "update public.families set manager_id = v_heir" in body
    assert "order by p.created_at limit 1" in body


def test_anon_cannot_ask():
    sql = _migration()

    assert "revoke all on function public.is_family_manager() from public, anon" in sql
