"""
בדיקות לניהול חברי המשפחה: הסרה, עזיבה והחלפת קוד הזמנה.

עד עכשיו מי שהצטרף למשפחה — בטעות, או עם קוד שדלף בקבוצת וואטסאפ —
נשאר בה לתמיד. אין מסלול להסיר אותו, אין דרך לעזוב, והקוד נוצר פעם אחת
ואי אפשר לשנותו. כלומר דליפה של שישה תווים היא גישה קבועה לכספי המשפחה,
למספרי הטלפון ולמקומות העבודה של כל חבריה.

המודל היה שטוח לגמרי. נוסף תפקיד אחד — מנהל המשפחה — והוא היחיד שרשאי
להסיר. הכללים נאכפים ב-DB; הבדיקות כאן מוודאות שהשכבה שמעליו לא מרככת
אותם ושהממשק לא מציע פעולות שייכשלו.
"""
from pathlib import Path

import pytest

from backend import app as app_module
from backend.app import app, limiter

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_ME    = "11111111-1111-1111-1111-111111111111"
_OTHER = "22222222-2222-2222-2222-222222222222"
_FAM   = "33333333-3333-3333-3333-333333333333"


@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    limiter.reset()
    # ברירת המחדל כאן היא מנהל: הבדיקות בקובץ הזה עוסקות במה שהפעולות
    # עושות, לא במי רשאי. הבדיקות על ההרשאה עצמה יושבות בקובץ נפרד.
    monkeypatch.setattr(app_module.db, "is_family_manager", lambda: True)
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]   = _ME
            sess["family_id"] = _FAM
        yield c
    limiter.reset()


# ─── הסרת חבר ────────────────────────────────────────────────────────────────

def test_removing_a_member_passes_the_transaction_choice_through(client, monkeypatch):
    """הבחירה על העסקאות היא של המשתמש; אסור שהשרת יכריע אותה בשקט."""
    seen = {}
    monkeypatch.setattr(app_module.db, "remove_family_member",
                        lambda uid, keep_transactions: (seen.update(
                            uid=uid, keep=keep_transactions) or (True, None)))

    client.delete(f"/api/family/members/{_OTHER}", json={"keep_transactions": False})

    assert seen == {"uid": _OTHER, "keep": False}


def test_keeping_transactions_is_the_default_when_nothing_is_said(client, monkeypatch):
    """בקשה בלי העדפה מפורשת לא אמורה למחוק כסף."""
    seen = {}
    monkeypatch.setattr(app_module.db, "remove_family_member",
                        lambda uid, keep_transactions: (seen.update(
                            keep=keep_transactions) or (True, None)))

    client.delete(f"/api/family/members/{_OTHER}", json={})

    assert seen["keep"] is True


def test_a_non_manager_is_refused_with_a_hebrew_reason(client, monkeypatch):
    """ה-DB מסרב באנגלית; המשתמש צריך לדעת למה."""
    monkeypatch.setattr(app_module.db, "remove_family_member",
                        lambda uid, keep_transactions:
                            (False, "only the family manager can remove members"))

    response = client.delete(f"/api/family/members/{_OTHER}", json={})

    assert response.status_code == 403
    assert "מנהל המשפחה" in response.get_json()["error"]


# ─── עזיבה ───────────────────────────────────────────────────────────────────

def test_leaving_updates_the_session_to_the_new_family(client, monkeypatch):
    """בלי זה ה-session ממשיך להצביע על המשפחה הישנה, כל שליפה מסוננת
    לפי משפחה שהמשתמש כבר לא חבר בה, והאפליקציה נראית ריקה."""
    monkeypatch.setattr(app_module.db, "leave_family",
                        lambda keep_transactions: ("44444444-4444-4444-4444-444444444444", None))

    client.post("/api/family/leave", json={})

    with client.session_transaction() as sess:
        assert sess["family_id"] == "44444444-4444-4444-4444-444444444444"


def test_a_failed_leave_does_not_move_the_session(client, monkeypatch):
    """בקרת-נגד: אסור שכישלון ישאיר את המשתמש מצביע לשום מקום."""
    monkeypatch.setattr(app_module.db, "leave_family",
                        lambda keep_transactions: (None, "boom"))

    client.post("/api/family/leave", json={})

    with client.session_transaction() as sess:
        assert sess["family_id"] == _FAM


# ─── החלפת קוד ───────────────────────────────────────────────────────────────

def test_rotating_returns_the_new_code_so_the_screen_can_show_it(client, monkeypatch):
    monkeypatch.setattr(app_module.db, "rotate_invite_code", lambda: ("NEW123", None))

    response = client.post("/api/family/invite-code")

    assert response.get_json()["invite_code"] == "NEW123"


# ─── הממשק ───────────────────────────────────────────────────────────────────

def test_escaping_the_transaction_dialog_keeps_the_money():
    """המלכודת. appConfirm מחזיר false על Escape, על לחיצה מחוץ לדיאלוג
    ועל ✕ — אז האפשרות ההרסנית חייבת להיות דווקא כפתור האישור, אחרת כל
    בריחה מהדיאלוג מוחקת עסקאות. זה בדיוק הבאג שקיים היום במחיקת פרויקט."""
    js = (_ROOT / "frontend/static/js/settings.js").read_text(encoding="utf-8")
    block = js[js.index("function askAboutTransactions"):][:900]

    assert "confirmText: 'למחוק אותן'" in block, \
        "האפשרות הבטוחה היא כפתור האישור — בריחה מהדיאלוג תמחק עסקאות"
    assert "return wipe ? WIPE : KEEP;" in block


def test_the_remove_button_is_only_offered_to_the_manager():
    """הכלל נאכף ב-DB ממילא; ההסתרה כאן היא כדי לא להציע פעולה שתיכשל."""
    html = (_ROOT / "frontend/templates/settings.html").read_text(encoding="utf-8")

    assert "user.id == family.get('manager_id')" in html
    assert "manager-badge" in html, "אין סימון של מנהל המשפחה ברשימת החברים"


def test_leaving_is_hidden_for_a_family_of_one():
    """לעזוב משפחה שאתה לבד בה זה רק ליצור משפחה ריקה אחרת."""
    html = (_ROOT / "frontend/templates/settings.html").read_text(encoding="utf-8")

    assert "{% if members | length > 1 %}" in html
