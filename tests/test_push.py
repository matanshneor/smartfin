"""התראות לטלפון (מתן, 31.10).

ההצפנה ממומשת אצלנו (‎backend/push.py‎), ולכן נבדקת מול וקטור הבדיקה של
התקן עצמו (RFC 8291, נספח A): אם הבייטים זהים, כל טלפון יפענח אותה.
"""
import json

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from backend import app as app_module
from backend import push
from backend import supabase_config as db
from backend.app import app, limiter

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"
_ME = "22222222-2222-2222-2222-222222222222"
_SALARY = "c-salary"


# ─── הצפנה וחתימה ───────────────────────────────────────────────────────────

def test_encryption_matches_the_rfc_8291_test_vector():
    server = ec.derive_private_key(
        int.from_bytes(push.b64u_decode("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"),
        ec.SECP256R1())
    body = push.encrypt(
        b"When I grow up, I want to be a watermelon",
        "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
        "BTBZMqHH6r4Tts7J_aSIgg",
        _server_key=server, _salt=push.b64u_decode("DGv6ra1nlYgDCS1FRnbzlw"))
    assert push.b64u(body) == (
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS"
        "6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Q"
        "ulcy4a-fN")


def test_the_vapid_token_is_a_valid_es256_signature(monkeypatch):
    private, public = push.generate_vapid_keys()
    monkeypatch.setenv("VAPID_PRIVATE_KEY", private)
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:test@example.com")
    header = push.vapid_header("https://fcm.googleapis.com/fcm/send/abc", now=1_800_000_000)
    token, key = header[len("vapid t="):].split(", k=")
    assert key == public == push.public_key()

    head, body, sig = token.split(".")
    claims = json.loads(push.b64u_decode(body))
    assert claims == {"aud": "https://fcm.googleapis.com", "exp": 1_800_000_000 + 12 * 3600,
                      "sub": "mailto:test@example.com"}
    raw = push.b64u_decode(sig)
    pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), push.b64u_decode(public))
    pub.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
               f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256()))


def test_without_a_key_nothing_is_sent(monkeypatch):
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    assert push.enabled() is False and push.public_key() is None
    assert push.send([{"endpoint": "https://fcm.googleapis.com/x", "p256dh": "a", "auth": "b"}],
                     {"title": "x"}) == []


@pytest.mark.parametrize("endpoint,ok", [
    ("https://fcm.googleapis.com/fcm/send/abc", True),
    ("https://web.push.apple.com/QGx", True),
    ("https://updates.push.services.mozilla.com/wpush/v2/x", True),
    ("http://fcm.googleapis.com/x", False),                 # לא https
    ("https://evil.example.com/x", False),                  # לא שירות התראות — SSRF
    ("https://fcm.googleapis.com.evil.com/x", False),
    ("https://169.254.169.254/latest", False),
])
def test_only_real_push_services_are_contacted(endpoint, ok):
    assert push._allowed_endpoint(endpoint) is ok


def test_dead_subscriptions_are_reported(monkeypatch):
    private, _ = push.generate_vapid_keys()
    monkeypatch.setenv("VAPID_PRIVATE_KEY", private)
    ua = ec.generate_private_key(ec.SECP256R1())
    sub = {"p256dh": push.b64u(push._point(ua.public_key())), "auth": push.b64u(b"0123456789abcdef")}
    sent = []

    class _Client:
        def __init__(self, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, content, headers):
            sent.append((url, headers["Content-Encoding"]))
            class R: status_code = 410 if url.endswith("gone") else 201
            return R()
    monkeypatch.setattr(push.httpx, "Client", _Client)

    dead = push.send([dict(sub, endpoint="https://fcm.googleapis.com/ok"),
                      dict(sub, endpoint="https://fcm.googleapis.com/gone"),
                      dict(sub, endpoint="https://evil.example.com/x")], {"title": "t"})
    assert dead == ["https://fcm.googleapis.com/gone"]
    assert [u for u, _ in sent] == ["https://fcm.googleapis.com/ok", "https://fcm.googleapis.com/gone"]
    assert {e for _, e in sent} == {"aes128gcm"}


# ─── נוסחים ─────────────────────────────────────────────────────────────────

def test_month_closed_reads_like_a_summary():
    m = push.month_closed(10, 14000, 11200, 800)
    assert m["title"] == "אוקטובר נסגר 📅"
    assert m["body"] == "הכנסות ₪14,000 · הוצאות ₪11,200 · חיסכון ₪800. נשארו ₪2,000"
    assert "גירעון של ₪500" in push.month_closed(10, 1000, 1500, 0)["body"]


def test_member_joined_does_not_guess_gender():
    body = push.member_joined("נועה", "משפחת שניאור")["body"]
    assert body == "נועה עכשיו חלק ממשפחת שניאור"
    assert "הצטרף" not in body


@pytest.mark.parametrize("weeks,phrase", [(1, "כבר שבוע"), (2, "כבר שבועיים"), (3, "כבר 3 שבועות")])
def test_quiet_week(weeks, phrase):
    m = push.quiet_week(weeks)
    assert phrase in m["title"] and m["url"] == "/import"


def test_last_installment_and_salary():
    assert "ACE: היום יורד התשלום האחרון, ₪400" in push.last_installment("ACE", 400)["body"]
    assert push.salary(14000, 11)["body"] == "משכורת של ₪14,000 נרשמה לנובמבר"


# ─── המסלולים ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _fresh_limits():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    private, _ = push.generate_vapid_keys()
    monkeypatch.setenv("VAPID_PRIVATE_KEY", private)
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"], sess["family_id"] = _ME, _FAM
        yield c


_KEYS = {"p256dh": "B" + "x" * 86, "auth": "y" * 22}


def test_subscribe_validates_and_remembers_the_device(client, monkeypatch):
    calls = []
    monkeypatch.setattr(app_module.db, "push_subscribe", lambda *a: calls.append(a) or True)
    ok = client.post("/api/push/subscribe", json={"endpoint": "https://fcm.googleapis.com/x", "keys": _KEYS})
    assert ok.status_code == 200 and calls == [("https://fcm.googleapis.com/x", _KEYS["p256dh"], _KEYS["auth"])]
    with client.session_transaction() as sess:
        assert sess["push_endpoint"] == "https://fcm.googleapis.com/x"

    bad = client.post("/api/push/subscribe", json={"endpoint": "https://evil.example.com/x", "keys": _KEYS})
    assert bad.status_code == 422 and len(calls) == 1


def test_logout_forgets_this_device(client, monkeypatch):
    gone = []
    monkeypatch.setattr(app_module.db, "push_subscribe", lambda *a: True)
    monkeypatch.setattr(app_module.db, "push_unsubscribe", gone.append)
    client.post("/api/push/subscribe", json={"endpoint": "https://fcm.googleapis.com/x", "keys": _KEYS})
    client.post("/logout")
    assert gone == ["https://fcm.googleapis.com/x"]


def test_the_daily_route_needs_the_secret(client, monkeypatch):
    monkeypatch.setenv("PUSH_CRON_SECRET", "s3cret")
    monkeypatch.setattr(app_module.db, "push_daily", lambda *a: pytest.fail("נקרא בלי סוד"))
    assert client.post("/internal/push/daily").status_code == 404
    assert client.post("/internal/push/daily", headers={"X-Cron-Secret": "nope"}).status_code == 404
    monkeypatch.delenv("PUSH_CRON_SECRET")
    assert client.post("/internal/push/daily", headers={"X-Cron-Secret": ""}).status_code == 404


def test_the_daily_route_sends_each_message_once_and_prunes(client, monkeypatch):
    monkeypatch.setenv("PUSH_CRON_SECRET", "s3cret")
    rows = [
        {"kind": "month_closed", "data": {"month": 10, "income": 100, "expense": 50, "savings": 0},
         "endpoint": "https://fcm.googleapis.com/a", "p256dh": "p", "auth": "a"},
        {"kind": "month_closed", "data": {"month": 10, "income": 100, "expense": 50, "savings": 0},
         "endpoint": "https://fcm.googleapis.com/b", "p256dh": "p", "auth": "a"},
        {"kind": "quiet_week", "data": {"weeks": 2},
         "endpoint": "https://fcm.googleapis.com/c", "p256dh": "p", "auth": "a"},
    ]
    seen = {}
    monkeypatch.setattr(app_module.db, "push_daily", lambda secret, today: seen.update(secret=secret) or rows)
    batches = []

    def _send(subs, msg):
        batches.append((msg["tag"], [s["endpoint"] for s in subs]))
        return ["https://fcm.googleapis.com/b"] if msg["tag"] == "month-closed" else []
    monkeypatch.setattr(app_module.push, "send", _send)
    forgot = []
    monkeypatch.setattr(app_module.db, "push_forget", lambda secret, eps: forgot.append((secret, eps)))

    res = client.post("/internal/push/daily", headers={"X-Cron-Secret": "s3cret"})
    assert res.get_json() == {"status": "ok", "sent": 3, "forgotten": 1}
    assert seen == {"secret": "s3cret"}
    assert sorted(batches) == [("month-closed", ["https://fcm.googleapis.com/a", "https://fcm.googleapis.com/b"]),
                               ("quiet-week", ["https://fcm.googleapis.com/c"])]
    assert forgot == [("s3cret", ["https://fcm.googleapis.com/b"])]


def test_a_salary_notifies_the_family_once_a_month(client, monkeypatch):
    cats = [{"id": _SALARY, "name": "משכורת", "icon": "💼", "type": "income"}]
    monkeypatch.setattr(app_module.db, "get_categories", lambda *a, **k: cats)
    monkeypatch.setattr(app_module, "family_settings", lambda: dict(db.DEFAULT_FAMILY_SETTINGS))
    monkeypatch.setattr(app_module.db, "get_profile", lambda *a: {"workplace": None})
    monkeypatch.setattr(app_module.db, "add_transaction", lambda p: (dict(p, id="t1"), None))
    monkeypatch.setattr(app_module, "_budget_note", lambda *a: None)
    asked, sent = [], []
    monkeypatch.setattr(app_module.db, "push_family_targets", lambda *a: asked.append(a) or [{"endpoint": "e"}])
    monkeypatch.setattr(app_module.push, "send_in_background", lambda subs, msg: sent.append(msg["body"]))

    res = client.post("/api/transactions", json={"amount": 14000, "type": "income",
                                                 "date": "2026-11-10", "category_id": _SALARY})
    assert res.status_code == 201
    assert asked == [("salary", "2026-11")]
    assert sent == ["משכורת של ₪14,000 נרשמה לנובמבר"]


def test_the_settings_toggle_only_appears_when_push_is_configured():
    from pathlib import Path
    html = (Path(__file__).resolve().parent.parent / "frontend/templates/settings.html").read_text(encoding="utf-8")
    block = html[html.index("{% if push_key %}"):]
    assert 'id="pushSettings"' in block[:block.index("{% endif %}")]
    sw = (Path(__file__).resolve().parent.parent / "frontend/static/sw.js").read_text(encoding="utf-8")
    assert "addEventListener('push'" in sw and "addEventListener('notificationclick'" in sw
