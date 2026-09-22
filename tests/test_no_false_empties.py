"""עשרה שולפים הפכו "השאילתה נכשלה" ל"אין לך נתונים".

זה הדפוס שה-docstring בראש ‎supabase_config.py‎ אומר שחוסל — והוא הוחל
על שולפי הסיכומים בלבד. מה שנשאר:

- ‎get_months_archive‎ נכשל → רצועת החודשים מתכווצת לחודש הנוכחי ועמוד
  ההשוואה מרונדר ריק. משפחה עם שנתיים היסטוריה רואה "אין היסטוריה".
- ‎get_recurring_transactions‎ נכשל → ‎summarise_recurring([])‎ → הפאנל
  כולו מוסתר. ₪11,000 של הוצאות קבועות נעלמים מהמסך.
- ‎_fetch_family_members‎ נכשל → ‎_resolve_owner‎ דוחה **כל** בעלים עם
  "בן המשפחה שנבחר אינו במשפחה שלך". השגיאה מאשימה את המשתמש.

אפס מדומה נראה בדיוק כמו אפס אמיתי, וכל האפליקציה היא מספרים.
"""
import pytest

from backend import supabase_config as db

pytestmark = pytest.mark.unit

_READERS = [
    ("get_recent_transactions",  ("fam",)),
    ("get_month_transactions",   ("fam", 2026, 9)),
    ("get_recurring_transactions", ("fam",)),
    ("get_projects",             ("fam", "viewer")),
    ("get_monthly_trend",        ("fam",)),
    ("get_months_archive",       ("fam",)),
    ("get_project_categories",   ("proj", "fam")),
    ("_fetch_family_members",    ("fam",)),
]


class _Exploding:
    """כל שאילתה נכשלת — המצב שהשולפים בלעו."""

    def table(self, *a, **k):        return self
    def select(self, *a, **k):       return self
    def eq(self, *a, **k):           return self
    def gte(self, *a, **k):          return self
    def lte(self, *a, **k):          return self
    def order(self, *a, **k):        return self
    def limit(self, *a, **k):        return self
    def single(self, *a, **k):       return self
    def maybe_single(self, *a, **k): return self
    def or_(self, *a, **k):          return self
    def rpc(self, *a, **k):          return self
    def execute(self):
        raise RuntimeError("המסד לא זמין")


@pytest.fixture
def broken(monkeypatch):
    monkeypatch.setattr(db, "get_client", lambda: _Exploding())


@pytest.mark.parametrize("name,args", _READERS, ids=[r[0] for r in _READERS])
def test_a_failed_read_is_raised_and_not_returned_as_empty(broken, name, args):
    """הלב. רשימה ריקה היא תשובה על המציאות, ושאילתה שנכשלה אינה כזו."""
    fn = getattr(db, name)

    with pytest.raises(db.DataUnavailable):
        fn(*args)


def test_the_app_turns_that_into_a_page_that_says_so():
    """בלי מטפל ייעודי זה 500 גנרי — נכון בכיוון, אבל לא אומר למשתמש
    שכדאי פשוט לנסות שוב.

    נבדק על המטפל עצמו ולא דרך בקשה: ‎app.config["TESTING"]‎ דולף בין
    בדיקות, ועם הדגל דלוק Flask מרים את החריגה במקום להפעיל מטפלים —
    כך שהבדיקה הייתה מודדת את הדגל ולא את ההתנהגות."""
    from backend.app import app, data_unavailable

    with app.test_request_context("/month"):
        body, status = data_unavailable(db.DataUnavailable("בדיקה"))

    assert status == 503, "כשל שליפה חייב להיות 503 ולא 200 ולא 500"
    assert "לא הצלחנו לטעון" in body


def test_an_api_caller_gets_json_and_not_an_html_page():
    """הדפדפן מבקש JSON, ודף HTML בתשובה מגיע אליו כ"שגיאת רשת" —
    כלומר הוא ינסה שוב ושוב בקשה שלא תצליח."""
    from backend.app import app, data_unavailable

    with app.test_request_context("/api/transactions",
                                  headers={"Accept": "application/json"}):
        response, status = data_unavailable(db.DataUnavailable("בדיקה"))

    assert status == 503
    assert response.is_json
    assert "לא הצלחנו לטעון" in response.get_json()["error"]


def test_the_failure_is_logged_at_a_level_that_reaches_sentry(caplog):
    """‎warning‎ הוא פירור ולא אירוע. כשל שליפה בפרודקשן חייב להישמע."""
    import logging
    from backend.app import app, data_unavailable

    with app.test_request_context("/month"), caplog.at_level(logging.ERROR):
        data_unavailable(db.DataUnavailable("בדיקה"))

    assert any(r.levelno >= logging.ERROR for r in caplog.records)
