"""
בדיקות לפתיחת קבלה מצורפת.

הסמל 📎 לא עשה כלום ב-iPhone. הקוד שלף כתובת מהשרת ב-fetch ואז קרא
ל-window.open — וב-iOS זה נחסם תמיד: הדפדפן מתיר פתיחת חלון רק כתוצאה
ישירה מלחיצה, וההמתנה לשרת מנתקת את הקשר. אין חלון, אין שגיאה, אין רמז.

התוצאה בפועל: הקבלות שנסרקו לא היו נגישות מהאפליקציה בטלפון בכלל.
"""
from pathlib import Path

import pytest

from backend import app as app_module
from backend.app import app

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_TX   = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def client(monkeypatch):
    # נוגעת בלקוח המשותף, ובבדיקת יחידה אין כזה
    monkeypatch.setattr(app_module.db, "set_auth_token", lambda t: None)
    monkeypatch.setattr(app_module.db, "get_family", lambda *a, **k: {})
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]      = "22222222-2222-2222-2222-222222222222"
            sess["family_id"]    = "33333333-3333-3333-3333-333333333333"
            sess["access_token"] = "tok"
        yield c


# ─── התיקון עצמו ─────────────────────────────────────────────────────────────

def test_the_badge_is_a_link_the_browser_can_follow(monkeypatch):
    """הלב: ניווט שנובע מלחיצה לא נחסם, פתיחת חלון אחרי המתנה כן."""
    for page in ("index.html", "month.html", "project_detail.html"):
        html = (_ROOT / "frontend/templates" / page).read_text(encoding="utf-8")
        assert 'class="receipt-badge" href=' in html, f"{page}: הסמל עדיין לא קישור"
        assert 'data-receipt-id' not in html, f"{page}: נשאר הכפתור הישן"


def test_no_javascript_opens_the_receipt_any_more():
    """מתעלמים מהערות: המילה window.open מופיעה שם בהסבר על התיקון,
    ובדיקה שתיפול על הסבר היא בדיקה שמישהו ימחק במקום לתקן."""
    import re
    js = (_ROOT / "frontend/static/js/transactions.js").read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)          # בלוקי הערות
    code = re.sub(r"^\s*//.*$", "", code, flags=re.M)         # הערות שורה

    assert "window.open" not in code, "עדיין נפתח חלון מ-JS — ייחסם ב-iOS"


def test_the_row_handlers_still_ignore_the_badge():
    """בלי ההחרגה, לחיצה על הסמל פותחת גם את מודאל העריכה."""
    js = (_ROOT / "frontend/static/js/transactions.js").read_text(encoding="utf-8")

    assert js.count("closest('.receipt-badge')") >= 1
    assert js.count(".receipt-badge, .delete-recurring-btn, .swipe-action") >= 3


def test_the_badge_has_a_real_tap_target():
    """22px בתוך שורה שגם נגררת וגם נלחצת — פספוס פותח עריכה במקום קבלה."""
    css = (_ROOT / "frontend/static/css/style.css").read_text(encoding="utf-8")
    block = css[css.index(".receipt-badge::before"):][:220]

    assert "width: 40px" in block and "height: 40px" in block


# ─── המסלול ──────────────────────────────────────────────────────────────────

def test_it_redirects_to_the_signed_url(client, monkeypatch):
    monkeypatch.setattr(app_module.db, "get_transaction_receipt_path",
                        lambda tx, fam: "fam/abc.webp")
    monkeypatch.setattr(app_module.db, "get_receipt_signed_url",
                        lambda token, path: ("https://x.supabase.co/signed", None))

    response = client.get(f"/receipts/{_TX}")

    assert response.status_code == 302
    assert response.headers["Location"] == "https://x.supabase.co/signed"


def test_the_signed_url_is_never_cached(client, monkeypatch):
    """קצרת-מועד ואישית — לא אמורה לשבת במטמון של proxy."""
    monkeypatch.setattr(app_module.db, "get_transaction_receipt_path",
                        lambda tx, fam: "fam/abc.webp")
    monkeypatch.setattr(app_module.db, "get_receipt_signed_url",
                        lambda token, path: ("https://x.supabase.co/signed", None))

    assert client.get(f"/receipts/{_TX}").headers["Cache-Control"] == "no-store"


def test_a_missing_receipt_shows_a_page_not_json(client, monkeypatch):
    """זו לשונית שנפתחה בדפדפן. JSON גולמי שם הוא מסך שבור."""
    monkeypatch.setattr(app_module.db, "get_transaction_receipt_path",
                        lambda tx, fam: None)

    response = client.get(f"/receipts/{_TX}")

    assert response.status_code == 404
    assert response.mimetype == "text/html"


def test_it_is_not_under_api_so_an_expired_session_goes_to_the_login_page():
    """תחת /api/ סשן שפג היה מחזיר 401 JSON ללשונית חדשה, במקום להעביר
    להתחברות. זה ניווט של הדפדפן, לא קריאת רקע."""
    app.config["TESTING"] = True
    response = app.test_client().get(f"/receipts/{_TX}")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
