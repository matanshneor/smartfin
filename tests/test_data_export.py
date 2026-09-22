"""הזכות לקחת את הנתונים ולעזוב לא סופקה בפועל.

הייצוא היחיד היה ‎/month.csv‎: חודש בודד, מגיע רק מעמוד החודש, בלי
הפרופיל, בלי הקטגוריות ובלי הפרויקטים. מי שרצה את הנתונים שלו היה
צריך לייצא חודש-חודש ביד ולהרכיב אותם לבד — וזו לא ניידות, זו משימה.

מדיניות הפרטיות מבטיחה זכות עיון, ו-‎/month.csv‎ קיים בדיוק בשביל
"מה קורה אם ארצה לעזוב". הוא פשוט לא ענה על זה.
"""
import json
from pathlib import Path

import pytest

from backend import supabase_config as db
from backend.app import app, limiter
from tests._fake_db import FakeSupabase

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_FAM = "11111111-1111-1111-1111-111111111111"
_ME = "22222222-2222-2222-2222-222222222222"
_MATE = "33333333-3333-3333-3333-333333333333"


@pytest.fixture
def exporting(monkeypatch):
    limiter.reset()
    app.config["TESTING"] = True

    fake = FakeSupabase(transactions=[
        {"id": "t1", "family_id": _FAM, "amount": 100.0, "type": "expense",
         "date": "2026-09-01", "project_id": None},
        {"id": "t2", "family_id": _FAM, "amount": 200.0, "type": "expense",
         "date": "2026-08-01", "project_id": "mine"},
        {"id": "t3", "family_id": _FAM, "amount": 300.0, "type": "expense",
         "date": "2026-07-01", "project_id": "theirs"},
    ])
    monkeypatch.setattr(db, "get_client", lambda: fake)
    monkeypatch.setattr(db, "get_profile", lambda uid: {"id": uid, "name": "מתן"})
    monkeypatch.setattr(db, "get_family",
                        lambda fid: {"id": fid, "name": "שניאור", "invite_code": "K4F2QX"})
    monkeypatch.setattr(db, "get_family_members",
                        lambda fid: [{"id": _ME, "name": "מתן"}, {"id": _MATE, "name": "אור"}])
    monkeypatch.setattr(db, "get_categories",
                        lambda fid: [{"id": "c1", "name": "מכולת", "type": "expense"}])
    # "mine" משותף/שלי, "theirs" אישי של בן משפחה אחר — לא אמור להיכלל
    monkeypatch.setattr(db, "get_projects",
                        lambda fid, viewer: [{"id": "mine", "name": "שיפוץ"}])

    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = _ME
            sess["family_id"] = _FAM
        yield c, fake


# ─── מה שנמצא בקובץ ──────────────────────────────────────────────────────────

def test_the_export_carries_everything_and_not_one_month(exporting):
    """הלב: פרופיל, משפחה, חברים, קטגוריות, פרויקטים וכל העסקאות."""
    c, _ = exporting

    res = c.get("/account.json")

    assert res.status_code == 200
    data = json.loads(res.get_data(as_text=True))
    for key in ("profile", "family", "members", "categories",
                "projects", "transactions", "exported_at"):
        assert key in data, f"{key} חסר בייצוא"


def test_it_downloads_as_a_file_and_does_not_open_in_the_tab(exporting):
    c, _ = exporting

    res = c.get("/account.json")

    assert "attachment" in res.headers.get("Content-Disposition", "")
    assert "smartfin-" in res.headers["Content-Disposition"]


def test_hebrew_survives_the_round_trip(exporting):
    """‎ensure_ascii‎ היה הופך כל שם קטגוריה לרצף ‎\\uXXXX‎ — קובץ תקין
    שאי אפשר לקרוא."""
    c, _ = exporting

    body = c.get("/account.json").get_data(as_text=True)

    assert "שניאור" in body
    assert "\\u05e9" not in body


# ─── ומה שלא ─────────────────────────────────────────────────────────────────

def test_a_personal_project_of_another_member_is_not_exported(exporting):
    """ייצוא לא עוקף פרטיות בתוך המשפחה. פרויקט אישי של בן משפחה אחר
    מוסתר בכל שאר האפליקציה, וקובץ הייצוא הוא בדיוק המקום שבו קל לשכוח
    את זה."""
    c, _ = exporting

    data = json.loads(c.get("/account.json").get_data(as_text=True))
    ids = {t["id"] for t in data["transactions"]}

    assert "t3" not in ids, "עסקה של פרויקט אישי של אחר נכללה בייצוא"
    assert {"t1", "t2"} <= ids, "עסקאות לגיטימיות נחסמו"


def test_it_needs_a_session():
    limiter.reset()
    app.config["TESTING"] = True
    with app.test_client() as c:
        res = c.get("/account.json")

    assert res.status_code in (302, 401)


def test_a_failed_read_is_not_exported_as_an_empty_account():
    """ייצוא ריק נראה בדיוק כמו חשבון ריק, ומי שמוריד אותו לפני מחיקת
    חשבון מקבל קובץ שאין בו כלום ולא יודע.

    נבדק על המקור ולא דרך בקשה: ‎app.config["TESTING"]‎ דולף בין בדיקות,
    ועם הדגל דלוק Flask מרים את החריגה במקום להפעיל את המטפל — כך
    שהבדיקה הייתה מודדת את הדגל."""
    src = (_ROOT / "backend/app.py").read_text(encoding="utf-8")
    fn = src[src.index("def export_account():"):]
    fn = fn[:fn.index("\n@app.route")]

    assert "db.export_account_data" in fn
    assert "except" not in fn, \
        "המסלול תופס את הכשל — המטפל הגלובלי (503) לא ירוץ, והמשתמש יקבל קובץ"


def test_the_reader_itself_raises_instead_of_returning_an_empty_dict():
    src = (_ROOT / "backend/supabase_config.py").read_text(encoding="utf-8")
    fn = src[src.index("def export_account_data("):]
    fn = fn[:fn.index("\ndef ")]

    assert "raise DataUnavailable" in fn
    assert "return {}" not in fn


# ─── ושהמסך מציע אותו ────────────────────────────────────────────────────────

def test_settings_offers_the_export_next_to_account_deletion():
    """זכות שקיימת רק כ-URL שאף אחד לא יודע עליו אינה זכות."""
    html = (_ROOT / "frontend/templates/settings.html").read_text(encoding="utf-8")

    assert "export_account" in html
    assert "ייצוא הנתונים שלי" in html


def test_the_export_is_rate_limited():
    """שאילתה שמושכת את כל ההיסטוריה של המשפחה."""
    src = (_ROOT / "backend/app.py").read_text(encoding="utf-8")
    after = src[src.index('@app.route("/account.json")'):]

    assert "@limiter.limit" in after[:after.index("\ndef ")]


# ─── והמדיניות אומרת את האמת ────────────────────────────────────────────────
#
# שתי טענות היו שגויות. "מחיקת החשבון מסירה את הפרופיל ואת הנתונים
# הקשורים אליו" ו"הנתונים נשמרים כל עוד החשבון פעיל" — בזמן ש-
# ‎owner_archive‎ שמר הכול לנצח, בלי שום קוד שמנקה. ובנפרד: תמונות
# הקבלות נשלחות ל-OpenAI, כלומר יוצאות מהאיחוד האירופי, והמדיניות
# פירטה רק ספקים אירופיים.

_PRIVACY = (_ROOT / "frontend/templates/privacy.html").read_text(encoding="utf-8")


def test_the_policy_states_the_archive_retention_window():
    """הבטחת מחיקה שלא מתקיימת גרועה יותר מהיעדר הבטחה."""
    assert "30 יום" in _PRIVACY, "חלון השימור של הארכיון לא מוצהר"
    assert "90 יום" in _PRIVACY, "שימור רישום הכניסות לא מוצהר"


def test_the_stated_window_matches_what_the_database_actually_does():
    """שני מספרים שאפשר לשנות בנפרד הם הבטחה שתתיישן בשקט."""
    sql = (_ROOT / "backend/supabase/migrations"
           / "20260922160000_archive_retention.sql").read_text(encoding="utf-8")

    assert "interval '30 days'" in sql
    assert "interval '90 days'" in sql


def test_the_policy_says_receipt_images_leave_the_eu():
    """המדיניות מפרטת את Supabase ו-Railway כאירופיים ומזכירה את OpenAI
    — בלי לומר שהתמונה עוזבת את האיחוד. זו העברה בינלאומית (44-49)."""
    assert "ארצות הברית" in _PRIVACY


def test_the_policy_names_who_is_responsible():
    """סעיף 13(1)(a): כתובת Gmail לבדה אינה זהות בקר."""
    assert "האחראי על המידע" in _PRIVACY
