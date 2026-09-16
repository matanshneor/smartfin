"""
בדיקות לתקציב יעד לקטגוריה.

עד היום הפס שליד כל קטגוריה מדד כמה היא מתוך סך ההוצאות החודש — "מכולת
היא 35% מההוצאות" — ולא "נשאר לך ₪200". וההתראה היחידה השוותה לממוצע
שלושת החודשים הקודמים, כלומר להרגל ולא להחלטה: מי שהוציא יותר מדי שלושה
חודשים ברצף מעלה את הממוצע, והאפליקציה מפסיקה להתריע. היא מתרגלת.

שתי החלטות נפרדות לכל קטגוריה, לפי בקשת מתן: האם יש תקציב, ואם כן —
האם להתריע בחריגה.
"""
import pytest

from backend import app as app_module
from backend import supabase_config as db
from backend.app import app, limiter

pytestmark = pytest.mark.unit

_CAT = "11111111-1111-1111-1111-111111111111"


def _settings(amount=2000, alert=True):
    return {"limits": {_CAT: {"amount": amount, "alert": alert}}}


def _rows(total):
    return [{"category_id": _CAT, "name": "מכולת", "icon": "🛒", "total": total}]


# ─── החישוב ──────────────────────────────────────────────────────────────────

def test_a_category_under_budget_shows_what_is_left():
    row = db.apply_budgets(_rows(1800), _settings())[0]

    assert row["budget_left"] == 200
    assert row["budget_pct"] == 90
    assert row["budget_over"] is False


def test_a_category_over_budget_shows_by_how_much():
    row = db.apply_budgets(_rows(2350), _settings())[0]

    assert row["budget_over"] is True
    assert row["budget_excess"] == 350
    assert row["budget_left"] == -350


def test_the_bar_stops_at_full_rather_than_overflowing():
    """פס שגולש מעבר לרוחב לא מוסיף מידע ושובר את הפריסה."""
    assert db.apply_budgets(_rows(9999), _settings())[0]["budget_pct"] == 100


def test_a_category_without_a_budget_is_untouched():
    """בקרת-נגד: מי שלא השתמש בתכונה לא אמור לראות שום שינוי."""
    row = db.apply_budgets(_rows(1800), {"limits": {}})[0]

    assert "budget" not in row
    assert row["total"] == 1800


@pytest.mark.parametrize("amount", [0, -5, None, "", "abc"])
def test_a_meaningless_budget_is_treated_as_none(amount):
    """‎0‎ הוא גם הדרך להסיר תקציב מהממשק, אז הוא חייב להיקרא כ'אין'."""
    assert db.category_budget({"limits": {_CAT: {"amount": amount}}}, _CAT) is None


def test_a_malformed_entry_does_not_crash_the_month_page():
    """ה-JSONB נערך בעבר ידנית; מבנה לא צפוי לא אמור להפיל עמוד."""
    for broken in (None, "2000", [], {"alert": True}):
        assert db.category_budget({"limits": {_CAT: broken}}, _CAT) is None


# ─── שתי ההחלטות, בנפרד ──────────────────────────────────────────────────────

def test_exceeding_a_budget_alerts_when_asked():
    alerts = db.budget_alerts(db.apply_budgets(_rows(2350), _settings(alert=True)))

    assert len(alerts) == 1
    assert "חריגה של ₪350" in alerts[0]["text"]
    assert "מכולת" in alerts[0]["text"]


def test_exceeding_a_budget_stays_quiet_when_not_asked():
    """הלב של מה שמתן ביקש: אפשר לראות את המספר בלי שינדנדו עליו."""
    alerts = db.budget_alerts(db.apply_budgets(_rows(2350), _settings(alert=False)))

    assert alerts == []


def test_staying_within_budget_never_alerts():
    assert db.budget_alerts(db.apply_budgets(_rows(1800), _settings())) == []


def test_alerting_defaults_to_on_when_a_budget_is_set():
    """מי שטרח לקבוע תקציב כנראה רוצה לדעת כשחרג; הכיבוי מפורש."""
    assert db.category_budget({"limits": {_CAT: {"amount": 2000}}}, _CAT)["alert"] is True


# ─── ההתראה מחליפה את זו של הממוצע ───────────────────────────────────────────

def test_a_budgeted_category_is_excluded_from_the_average_alert(monkeypatch):
    """שתי התראות על אותה קטגוריה הן רעש, והן סותרות: "40% מעל הממוצע"
    ליד "בתוך התקציב" מבלבל יותר משהוא מסביר."""
    monkeypatch.setattr(db, "_category_history_averages",
                        lambda f, y, m: ({"מכולת": 3000}, {"מכולת": {"a": 1000}}, {"מכולת": "🛒"}))
    monkeypatch.setattr(db, "get_client", lambda: object())

    with_skip = db.get_anomalies("f", 2026, 9, {"income": 1, "expense": 0, "remaining": 1},
                                 db.DEFAULT_FAMILY_SETTINGS, skip_categories=["מכולת"])
    without   = db.get_anomalies("f", 2026, 9, {"income": 1, "expense": 0, "remaining": 1},
                                 db.DEFAULT_FAMILY_SETTINGS)

    assert any("מהממוצע" in a["text"] for a in without), "הבדיקה לא בודקת כלום"
    assert not any("מהממוצע" in a["text"] for a in with_skip)


# ─── השמירה ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    limiter.reset()
    monkeypatch.setattr(app_module.db, "get_categories",
                        lambda fid: [{"id": _CAT, "name": "מכולת", "type": "expense"}])
    monkeypatch.setattr(app_module, "family_settings", lambda: dict(db.DEFAULT_FAMILY_SETTINGS))
    saved = {}
    monkeypatch.setattr(app_module.db, "update_family_settings",
                        lambda fid, patch: (saved.update(patch) or True))
    monkeypatch.setattr(app_module.db, "get_family_settings", lambda fid: saved)
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]   = "22222222-2222-2222-2222-222222222222"
            sess["family_id"] = "33333333-3333-3333-3333-333333333333"
        yield c, saved
    limiter.reset()


def test_setting_a_budget_stores_both_decisions(client):
    c, saved = client

    c.put("/api/family/settings", json={"limits": {_CAT: {"amount": 2000, "alert": False}}})

    assert saved["limits"][_CAT] == {"amount": 2000.0, "alert": False}


def test_clearing_the_amount_removes_the_budget(client):
    """"לא להגדיר תקציב" ו"להסיר תקציב" הם אותו מסלול — אין פעולת
    מחיקה נפרדת שאפשר לשכוח."""
    c, saved = client
    c.put("/api/family/settings", json={"limits": {_CAT: {"amount": 2000}}})

    c.put("/api/family/settings", json={"limits": {_CAT: {"amount": ""}}})

    assert _CAT not in saved["limits"]


def test_a_budget_for_a_category_of_another_family_is_refused(client):
    """הסכומים מגיעים מהלקוח, כולל המזהה."""
    c, _ = client

    response = c.put("/api/family/settings",
                     json={"limits": {"99999999-9999-9999-9999-999999999999": {"amount": 100}}})

    assert response.status_code == 422


@pytest.mark.parametrize("bad", [-5, "abc", 1e400])
def test_a_nonsense_amount_is_refused(client, bad):
    c, _ = client

    assert c.put("/api/family/settings",
                 json={"limits": {_CAT: {"amount": bad}}}).status_code == 422
