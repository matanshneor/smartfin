""""החשבון שלי" (מתן, 13.10), ו-Face ID שהוסר.

"החשבון שלי" — כמו "עסקאות קבועות": שורה שלמה היא הכפתור, בלי כפתורי "עדכון".
Face ID הוסר לגמרי (מתן, 13.10): באייפון אתר לא יכול לפתוח Face ID ישירות —
אפל מציגה קודם חלון "התחברות אל railway.app" ומחכה ללחיצה. "אני רוצה שהאתר
פשוט יזהה אותי" — ההתחברות נשמרת (‎web_sessions‎), אז נכנסים ישר."""
from pathlib import Path

import pytest

from backend.app import app


def _noop():
    return "ok"


app.add_url_rule("/__test/old-lock", "test_old_lock", _noop)

pytestmark = pytest.mark.unit
_ROOT = Path(__file__).resolve().parent.parent


def test_my_account_rows_look_like_the_recurring_list():
    html = (_ROOT / "frontend/templates/settings.html").read_text(encoding="utf-8")
    mine = html[html.index('id="my-details"'):]
    mine = mine[:mine.index("</section>")]
    for el in ("editProfileBtn", "memberColorOpen", "toggleEmailBtn", "togglePhoneBtn", "togglePasswordBtn"):
        assert 'class="acct-row' in mine and f'id="{el}"' in mine, el
    for old in ("עדכון כתובת מייל", "עדכון מספר טלפון", ">עדכון סיסמה<", ">עדכון</button>"):
        assert old not in mine, old
    for title in ("פרטים", "התחברות"):
        assert f'<p class="recurring-group-title">{title}</p>' in mine


def test_face_id_is_gone_everywhere():
    for rel in ("frontend/static/js/passkey.js", "frontend/static/js/face-lock.js",
                "frontend/templates/unlock.html"):
        assert not (_ROOT / rel).exists(), rel
    for rel in ("frontend/templates/login.html", "frontend/templates/settings.html",
                "frontend/templates/base.html", "frontend/static/js/auth-guard.js",
                "frontend/static/js/whats-new.js", "frontend/templates/landing.html",
                "backend/app.py", "backend/supabase_config.py"):
        text = (_ROOT / rel).read_text(encoding="utf-8")
        for word in ("passkey", "face_lock", "/unlock", "data-face-lock"):
            assert word not in text, (rel, word)
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert not [r for r in rules if "passkey" in r or "unlock" in r or r == "/api/alive"]


def test_an_old_session_that_was_locked_just_goes_in(monkeypatch):
    """מי שהיה עם ‎face_lock‎ בעוגייה לפני ההסרה — נכנס ישר, בלי מסך נעילה."""
    import time
    from backend import app as app_module
    monkeypatch.setattr(app_module.db, "set_auth_token", lambda _t: None)
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"; s["family_id"] = None; s["access_token"] = "a"; s["refresh_token"] = "r"
        s["token_expires_at"] = time.time() + 3000
        s["face_lock"] = True; s["locked"] = True; s["last_seen"] = 0
    assert c.get("/__test/old-lock").status_code == 200


def test_fixed_and_variable_sit_small_beside_the_donut():
    """מתן (13.10): "בלי הפס ובלי הכיתוב — שיהיה כתוב בצד הגרף בקטן"."""
    tpl = (_ROOT / "frontend/templates/month.html").read_text(encoding="utf-8")
    assert "fixed-split" not in tpl
    corner = tpl[tpl.index('<div class="split-corner">'):]
    corner = corner[:corner.index("</div>")]
    assert "קבועות" in corner and "משתנות" in corner          # שתיהן באותו צד
    src = (_ROOT / "backend/app.py").read_text(encoding="utf-8")
    assert 'fixed_split = {"fixed": fixed_total, "variable": round(exp_total - fixed_total, 2)}' in src


def test_opening_a_category_closes_the_others():
    """מתן (13.10): "כאשר לוחצים על קטגוריה אחת — האחרות נסגרות מיד"."""
    for name in ("month.js", "project-detail.js"):
        js = (_ROOT / "frontend/static/js" / name).read_text(encoding="utf-8")
        assert "if (isOpen) closeOtherCategories(trigger, wrap);" in js, name
