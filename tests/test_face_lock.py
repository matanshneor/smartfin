"""נעילה ב-Face ID (מתן, 13.10): "כל פעם שפותחים את האפליקציה — נכנסים ישר.
מי שהגדיר סריקת פנים — סריקת פנים, ומי שלא — ישר". אחרי 5 דקות ברקע;
אם הסריקה נכשלה — "נסו שוב" או "כניסה עם סיסמה"."""
import time
from pathlib import Path

import pytest

from backend import app as app_module
from backend.app import app

pytestmark = pytest.mark.unit
_ROOT = Path(__file__).resolve().parent.parent
ME = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _quiet_db(monkeypatch):
    monkeypatch.setattr(app_module.db, "set_auth_token", lambda _t: None)
    monkeypatch.setattr(app_module.db, "web_session_close", lambda sid: None)
    monkeypatch.setattr(app_module.db, "web_session_open", lambda *a: None)


def _noop():
    return "ok"


app.add_url_rule("/__test/lock-page", "test_lock_page", _noop)
app.add_url_rule("/api/__test/lock-api", "test_lock_api", _noop)


def _client(face_lock=True, idle=0):
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = ME
        s["family_id"] = None
        s["access_token"] = "a"
        s["refresh_token"] = "r"
        s["token_expires_at"] = time.time() + 3000
        s["sid"] = "old-sid"
        if face_lock:
            s["face_lock"] = True
            s["last_seen"] = time.time() - idle
    return c


def test_without_face_id_you_just_go_in():
    r = _client(face_lock=False).get("/__test/lock-page")
    assert r.status_code == 200


def test_a_short_break_does_not_lock():
    assert _client(idle=40).get("/__test/lock-page").status_code == 200


def test_a_minute_away_locks_the_pages():
    r = _client(idle=90).get("/__test/lock-page?x=1")
    assert r.status_code == 302 and "/unlock?next=" in r.headers["Location"]
    assert "lock-page" in r.headers["Location"]


def test_a_locked_api_call_gets_423():
    r = _client(idle=90).get("/api/__test/lock-api")
    assert r.status_code == 423 and r.get_json()["locked"] is True


def test_staying_locked_until_unlocked():
    c = _client(idle=90)
    c.get("/__test/lock-page")
    with c.session_transaction() as s:
        s["last_seen"] = time.time()          # גם בקשה טרייה לא פותחת
    assert c.get("/__test/lock-page").status_code == 302


def test_the_unlock_screen_shows_while_locked():
    c = _client(idle=90)
    with c.session_transaction() as s:
        s["user_name"] = "מתן"
    r = c.get("/unlock?next=/month")
    body = r.get_data(as_text=True)
    assert r.status_code == 200 and "שלום, מתן" in body and "כניסה עם סיסמה" in body
    assert 'data-next="/month"' in body


def test_the_next_address_stays_inside_the_app():
    c = _client(idle=90)
    for bad in ("//evil.com", "https://evil.com", "/\\evil.com"):
        assert 'data-next="/"' in c.get("/unlock", query_string={"next": bad}).get_data(as_text=True), bad


def test_face_of_the_same_account_unlocks(monkeypatch):
    monkeypatch.setattr(app_module, "_passkey_body", lambda: ("ch", {"id": "x"}))
    monkeypatch.setattr(app_module.db, "passkey_login_verify", lambda ch, cred: (
        {"user": {"id": ME, "email": "m@x"}, "access_token": "a2", "refresh_token": "r2", "expires_at": 9e9}, None))
    monkeypatch.setattr(app_module, "_begin_session", lambda *a: app_module.session.update(
        {"user_id": ME, "access_token": "a2", "refresh_token": "r2", "token_expires_at": 9e9}) and None)
    c = _client(idle=90)
    c.get("/__test/lock-page")
    assert c.post("/api/unlock/verify", json={}).status_code == 200
    assert c.get("/__test/lock-page").status_code == 200


def test_face_of_another_account_does_not_unlock(monkeypatch):
    monkeypatch.setattr(app_module, "_passkey_body", lambda: ("ch", {"id": "x"}))
    monkeypatch.setattr(app_module.db, "passkey_login_verify", lambda ch, cred: (
        {"user": {"id": "someone-else"}, "access_token": "a", "refresh_token": "r", "expires_at": 1}, None))
    c = _client(idle=90)
    c.get("/__test/lock-page")
    assert c.post("/api/unlock/verify", json={}).status_code == 403
    assert c.get("/__test/lock-page").status_code == 302


def test_sign_in_with_password_leaves_to_the_login_form():
    c = _client(idle=90)
    r = c.post("/unlock/password")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    with c.session_transaction() as s:
        assert not s.get("user_id")


def test_the_heartbeat_keeps_an_open_app_unlocked():
    c = _client(idle=40)
    assert c.get("/api/alive").status_code == 200
    with c.session_transaction() as s:
        assert time.time() - s["last_seen"] < 5


def test_only_a_phone_where_face_id_worked_gets_the_lock():
    src = (_ROOT / "backend/app.py").read_text(encoding="utf-8")
    login = src[src.index("def passkey_login_verify_route"):src.index("# ─── נעילה ב-Face ID")]
    assert "_face_lock_on()" in login
    reg = src[src.index("def passkey_register_verify_route"):src.index("def passkeys_list_route")]
    assert "_face_lock_on()" in reg
    delete = src[src.index("def passkey_delete_route"):src.index("@app.route(\"/join/<code>\")")]
    assert 'session.pop("face_lock", None)' in delete


def test_the_phone_locks_itself_after_a_minute_in_the_background():
    js = (_ROOT / "frontend/static/js/face-lock.js").read_text(encoding="utf-8")
    assert "const LOCK_AFTER = 60 * 1000;" in js and "'/api/alive'" in js and "setInterval(beat, 20 * 1000);" in js
    assert app_module._LOCK_AFTER == 60      # דקה (מתן, 13.10)
    base = (_ROOT / "frontend/templates/base.html").read_text(encoding="utf-8")
    assert "data-face-lock" in base and "js/face-lock.js" in base
    guard = (_ROOT / "frontend/static/js/auth-guard.js").read_text(encoding="utf-8")
    assert "response.status === 423" in guard


def test_the_unlock_screen_scans_by_itself_and_offers_retry():
    js = (_ROOT / "frontend/static/js/passkey.js").read_text(encoding="utf-8")
    part = js[js.index("// ── מסך הנעילה"):js.index("// ── הגדרות → החשבון שלי")]
    assert "'/api/unlock/verify'" in part and "unlockBtn.click()" in part and "'נסו שוב עם '" in part


def test_my_account_rows_look_like_the_recurring_list():
    """"החשבון שלי" (מתן, 13.10): כמו "עסקאות קבועות" — שורה שלמה היא הכפתור,
    בלי כפתורי "עדכון"; Face ID — מתג. כיבוי שואל קודם."""
    html = (_ROOT / "frontend/templates/settings.html").read_text(encoding="utf-8")
    mine = html[html.index('id="my-details"'):]
    mine = mine[:mine.index("</section>")]
    for el in ("editProfileBtn", "memberColorOpen", "toggleEmailBtn", "togglePhoneBtn", "togglePasswordBtn"):
        assert f'class="acct-row' in mine and f'id="{el}"' in mine, el
    for old in ("עדכון כתובת מייל", "עדכון מספר טלפון", ">עדכון סיסמה<", ">עדכון</button>"):
        assert old not in mine, old
    for title in ("פרטים", "התחברות", "אבטחה"):
        assert f'<p class="recurring-group-title">{title}</p>' in mine
    js = (_ROOT / "frontend/static/js/passkey.js").read_text(encoding="utf-8")
    assert "title: 'לכבות את נעילת האפליקציה?'" in js
