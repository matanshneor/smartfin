"""כניסה עם Face ID (מתן, 12.10).

Passkeys של Supabase Auth. השרת מעביר בלבד: אתגר מ-Supabase, חתימה בדפדפן,
ו-Supabase בודק ומחזיר סשן — שנפתח בדיוק כמו בכניסה בסיסמה
(‎_begin_session‎).
"""
from pathlib import Path

import pytest

from backend import app as app_module
from backend import supabase_config as db
from backend.app import app

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_ME, _FAM = "22222222-2222-2222-2222-222222222222", "11111111-1111-1111-1111-111111111111"
_PK = "33333333-3333-3333-3333-333333333333"


class _Resp:
    def __init__(self, status, data):
        self.status_code, self._data = status, data
        self.content = b"x"

    def json(self):
        return self._data


@pytest.fixture
def http(monkeypatch):
    """httpx מדומה: רושם כל פנייה ומחזיר את התשובה שנקבעה לנתיב."""
    import httpx
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "anon")
    calls, answers = [], {}

    def fake(method):
        def go(url, **kw):
            calls.append((method, url, kw))
            path = url.split("/auth/v1", 1)[1]
            return answers.get((method, path), _Resp(404, {"error_code": "not_found"}))
        return go
    for m in ("get", "post", "delete"):
        monkeypatch.setattr(httpx, m, fake(m))
    return calls, answers


# ─── שכבת הנתונים ────────────────────────────────────────────────────────

def test_login_options_go_to_supabase(http):
    calls, answers = http
    answers[("post", "/passkeys/authentication/options")] = _Resp(200, {"challenge_id": "c1", "options": {}})
    data, err = db.passkey_login_options()
    assert err is None and data["challenge_id"] == "c1"
    assert calls[0][2]["headers"]["apikey"] == "anon" and "Authorization" not in calls[0][2]["headers"]


def test_registration_carries_the_users_own_token(http):
    calls, answers = http
    answers[("post", "/passkeys/registration/options")] = _Resp(200, {"challenge_id": "c2", "options": {}})
    db.passkey_register_options("user-jwt")
    assert calls[0][2]["headers"]["Authorization"] == "Bearer user-jwt"


def test_a_supabase_error_comes_back_as_its_code(http):
    _, answers = http
    answers[("post", "/passkeys/authentication/options")] = _Resp(422, {"error_code": "passkey_disabled"})
    assert db.passkey_login_options() == (None, "passkey_disabled")


def test_verify_returns_a_session(http):
    _, answers = http
    answers[("post", "/passkeys/authentication/verify")] = _Resp(200, {
        "access_token": "a", "refresh_token": "r", "expires_in": 3600, "user": {"id": _ME, "email": "m@x"}})
    sess, err = db.passkey_login_verify("c1", {"id": "cred"})
    assert err is None and sess["access_token"] == "a" and sess["expires_at"] > 0


def test_verify_without_a_session_is_a_failure(http):
    _, answers = http
    answers[("post", "/passkeys/authentication/verify")] = _Resp(200, {"msg": "ok"})
    assert db.passkey_login_verify("c1", {"id": "cred"}) == (None, "unavailable")


# ─── המסלולים ────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_signing_in_with_face_id_opens_the_same_session(client, monkeypatch):
    sess = {"access_token": "a", "refresh_token": "r", "expires_at": 9, "user": {"id": _ME, "email": "m@x"}}
    monkeypatch.setattr(db, "passkey_login_verify", lambda cid, cred: (sess, None))
    seen = {}

    def begin(user_id, email, access, refresh, expires):
        seen.update(user_id=user_id, access=access)
        from flask import session
        session["user_id"], session["family_id"] = user_id, _FAM
    monkeypatch.setattr(app_module, "_begin_session", begin)
    res = client.post("/api/passkey/login/verify", json={"challenge_id": "c1", "credential": {"id": "x"}})
    assert res.status_code == 200 and res.get_json()["ok"] is True
    assert seen == {"user_id": _ME, "access": "a"}
    assert "sf_returning=1" in res.headers.get("Set-Cookie", "")      # המכשיר מוכר מעכשיו
    with client.session_transaction() as s:
        assert s["user_id"] == _ME


def test_a_rejected_signature_does_not_sign_in(client, monkeypatch):
    monkeypatch.setattr(db, "passkey_login_verify", lambda cid, cred: (None, "webauthn_verification_failed"))
    res = client.post("/api/passkey/login/verify", json={"challenge_id": "c1", "credential": {"id": "x"}})
    assert res.status_code == 401
    with client.session_transaction() as s:
        assert "user_id" not in s


def test_a_malformed_body_never_reaches_supabase(client, monkeypatch):
    monkeypatch.setattr(db, "passkey_login_verify", lambda *a: pytest.fail("נשלח ל-Supabase"))
    for body in ({}, {"challenge_id": "c"}, {"challenge_id": 5, "credential": {}}, {"challenge_id": "c", "credential": "x"}):
        assert client.post("/api/passkey/login/verify", json=body).status_code == 400


def test_errors_are_said_in_hebrew(client, monkeypatch):
    monkeypatch.setattr(db, "passkey_login_options", lambda: (None, "passkey_disabled"))
    res = client.post("/api/passkey/login/options")
    assert res.status_code == 400 and res.get_json()["error"] == "הכניסה עם Face ID עוד לא הופעלה באתר"


def test_registering_and_managing_needs_a_signed_in_user(client):
    for method, url in (("post", "/api/passkey/register/options"), ("post", "/api/passkey/register/verify"),
                        ("get", "/api/passkeys"), ("delete", f"/api/passkeys/{_PK}")):
        res = getattr(client, method)(url, headers={"Accept": "application/json"})
        assert res.status_code == 401, url


def test_delete_takes_only_a_uuid(client, monkeypatch):
    monkeypatch.setattr(db, "set_auth_token", lambda t: None)
    monkeypatch.setattr(db, "passkey_delete", lambda *a: pytest.fail("נשלח ל-Supabase"))
    with client.session_transaction() as s:
        s["user_id"], s["family_id"], s["access_token"] = _ME, _FAM, "jwt"
    assert client.delete("/api/passkeys/..%2Fadmin", headers={"Accept": "application/json"}).status_code == 404


# ─── המסכים ──────────────────────────────────────────────────────────────

def test_the_login_button_is_hidden_until_the_phone_has_face_id():
    html = (_ROOT / "frontend/templates/login.html").read_text(encoding="utf-8")
    assert '<button type="button" class="passkey-btn" id="passkeyLogin" hidden>' in html
    js = (_ROOT / "frontend/static/js/passkey.js").read_text(encoding="utf-8")
    assert "if (loginBtn && supported && hasFlag())" in js


def test_settings_offers_it_under_my_account():
    html = (_ROOT / "frontend/templates/settings.html").read_text(encoding="utf-8")
    mine = html[html.index('id="my-details"'):]
    mine = mine[:mine.index("</section>")]
    assert 'id="passkeySettings" hidden' in mine and 'id="passkeyEnableBtn"' in mine
    assert "js/passkey.js" in html


def test_cancelling_the_system_prompt_is_not_an_error():
    js = (_ROOT / "frontend/static/js/passkey.js").read_text(encoding="utf-8")
    assert "e.name === 'NotAllowedError' || e.name === 'AbortError'" in js
