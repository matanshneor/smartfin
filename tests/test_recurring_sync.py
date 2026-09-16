"""
בדיקות למתי מנוע העסקאות הקבועות רץ.

הוא רץ רק מהדשבורד. מי שהגיע ישר לעמוד החודש — מסימנייה, מהתפריט התחתון
או מקישור — ראה חודש **בלי המשכורת ובלי ההוראות הקבועות**, בלי שום דבר
שיסביר למה. המספרים תוקנו רק אם במקרה עבר דרך דף הבית.

ובאג שני באותו מקום: הסימון "סונכרן להיום" נכתב גם כשהיצירה נכשלה, אז
הניסיון הבא היה רק למחרת. כשל שנראה כהצלחה משאיר חודש שלם חסר.
"""
import pytest

from backend import app as app_module
from backend.app import app

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    # שאר הדף לא מעניין כאן — רק מתי הסנכרון נקרא
    from backend import supabase_config as _db
    for fn, val in [
        ("get_family_settings", dict(_db.DEFAULT_FAMILY_SETTINGS)),
        ("get_monthly_summary", _db._empty_summary()),
        ("get_categories", []), ("get_family_members", []),
        ("family_has_no_transactions", False), ("get_recent_transactions", []),
        ("get_months_archive", []), ("get_monthly_trend", []),
        ("fetch_month_rows", []),
        ("get_month_transactions", []), ("get_category_breakdown", []),
        ("get_member_breakdown", []), ("get_anomalies", []),
        ("get_run_rate_forecasts", []), ("get_project_month_summary",
                                         {"transactions": [], "expense": 0, "income": 0}),
    ]:
        if hasattr(app_module.db, fn):
            monkeypatch.setattr(app_module.db, fn, lambda *a, _v=val, **k: _v)
    monkeypatch.setattr(app_module, "family_settings",
                        lambda: dict(_db.DEFAULT_FAMILY_SETTINGS))
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]   = "22222222-2222-2222-2222-222222222222"
            sess["family_id"] = _FAM
        yield c


# ─── מאילו עמודים זה רץ ──────────────────────────────────────────────────────

@pytest.mark.parametrize("path,why", [
    ("/",       "הדשבורד — היה היחיד"),
    ("/month",  "נפתח ישירות מסימנייה או מהתפריט, ומציג את כל מספרי החודש"),
    ("/months", "משווה חודשים — חודש חסר מעוות את ההשוואה"),
])
def test_opening_a_page_with_monthly_figures_fills_in_the_recurring_ones(
        client, monkeypatch, path, why):
    calls = []
    monkeypatch.setattr(app_module.db, "materialize_recurring",
                        lambda fid: (calls.append(fid) or (0, True)))

    client.get(path)

    assert calls == [_FAM], f"{path} לא מסנכרן — {why}"


def test_it_runs_once_a_day_and_not_on_every_page_load(client, monkeypatch):
    """בקרת-נגד: זו כתיבה למסד, לא שליפה. הרצה בכל טעינה הייתה מכפילה
    את עלות כל עמוד."""
    calls = []
    monkeypatch.setattr(app_module.db, "materialize_recurring",
                        lambda fid: (calls.append(fid) or (0, True)))

    client.get("/")
    client.get("/month")
    client.get("/months")

    assert len(calls) == 1, f"רץ {len(calls)} פעמים באותו יום"


# ─── כישלון לא מסמן הצלחה ────────────────────────────────────────────────────

def test_a_failed_run_is_retried_on_the_next_page_load(client, monkeypatch):
    """הלב של הבאג השני: סימון "סונכרן" אחרי כישלון דחה את הניסיון הבא
    למחר, והשאיר חודש בלי משכורת עד אז."""
    calls = []
    monkeypatch.setattr(app_module.db, "materialize_recurring",
                        lambda fid: (calls.append(fid) or (0, False)))

    client.get("/")
    client.get("/month")

    assert len(calls) == 2, "כישלון סומן כהצלחה — לא ינוסה שוב עד מחר"

    with client.session_transaction() as sess:
        assert "recurring_synced" not in sess


def test_a_successful_run_is_marked(client, monkeypatch):
    """בקרת-נגד: בלי הסימון זה היה רץ בכל טעינת עמוד."""
    monkeypatch.setattr(app_module.db, "materialize_recurring", lambda fid: (3, True))

    client.get("/")

    with client.session_transaction() as sess:
        assert sess.get("recurring_synced")


def test_a_family_less_account_is_skipped(client, monkeypatch):
    calls = []
    monkeypatch.setattr(app_module.db, "materialize_recurring",
                        lambda fid: (calls.append(fid) or (0, True)))
    with client.session_transaction() as sess:
        sess["family_id"] = None

    client.get("/")

    assert calls == []
