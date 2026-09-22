"""
בדיקות להסרת עסקה קבועה.

הדיאלוג בהגדרות מבטיח: "מופעים חדשים יפסיקו להיווצר. מופעים שכבר נוצרו
יישארו." בפועל הכפתור הריץ מחיקה מלאה של שורת התבנית — ושורת התבנית היא
עסקה אמיתית לכל דבר: היא המופע הראשון בסדרה, והיא נספרת בסיכום החודשי
(get_monthly_summary לא מסננת is_recurring). כלומר שכר הדירה של החודש
הראשון נמחק מההיסטוריה בשקט, בניגוד גמור להבטחה שהמשתמש הרגע קרא.

ובנוסף: המחיקה ניתקה את כל המופעים מהתבנית (on delete set null), כך
שמנגנון הדדופ הפסיק לראות אותם. מי שיצר את אותה עסקה קבועה מחדש קיבל
את כל החודשים בשנית — שכר דירה כפול על עשרה חודשים.
"""
from pathlib import Path

import pytest

from backend import app as app_module
from backend import supabase_config as db
from backend.app import app

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_TX = "11111111-1111-1111-1111-111111111111"
_FAM = "22222222-2222-2222-2222-222222222222"


class _FakeClient:
    """מתעד מה נעשה — עדכון או מחיקה — ואיזה שדות נשלחו."""

    def __init__(self):
        self.updated = None
        self.deleted = False

    def table(self, _n):            return self
    def update(self, payload, **k): self.updated = payload; return self
    def delete(self, **k):          self.deleted = True; return self
    def eq(self, *a, **k):          return self
    def execute(self):              return self

    @property
    def data(self):                 return [{"id": _TX}]


@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    fake = _FakeClient()
    monkeypatch.setattr(db, "get_client", lambda: fake)
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]   = "33333333-3333-3333-3333-333333333333"
            sess["family_id"] = _FAM
        yield c, fake


# ─── ההבטחה שבדיאלוג ─────────────────────────────────────────────────────────

def test_removing_a_recurring_series_does_not_delete_the_transaction(client):
    """הלב: שורת התבנית היא כסף שזז באמת, ואסור שתיעלם."""
    c, fake = client

    response = c.delete(f"/api/recurring/{_TX}")

    assert response.status_code == 200
    assert fake.deleted is False, "העסקה נמחקה — כסף אמיתי הוצא מההיסטוריה"
    assert fake.updated is not None


def test_removing_a_recurring_series_does_stop_future_occurrences(client):
    """בקרת-נגד: אם לא כיבינו את הדגל, לא עשינו כלום."""
    c, fake = client

    c.delete(f"/api/recurring/{_TX}")

    assert fake.updated["is_recurring"] is False
    assert fake.updated["recurring_frequency"] is None


def test_the_dialog_no_longer_promises_something_the_code_does_not_do():
    """ההודעה והקוד חייבים להסכים; הם לא הסכימו, וזה היה כל הבאג."""
    # המטפל עבר מ-settings.js ל-transactions.js כשאותה רשימה נוספה
    # לעמוד החודש. הבדיקה מחפשת אותו איפה שהוא — קיבוע שם הקובץ הוא
    # שהפיל אותה, ולא שום שינוי בהתנהגות שהיא באמת שומרת עליה.
    owners = [f for f in (_ROOT / "frontend/static/js").glob("*.js")
              if "להסיר את העסקה הקבועה?" in f.read_text(encoding="utf-8")]
    assert len(owners) == 1, f"הדיאלוג מופיע ב-{[f.name for f in owners]} — עותק כפול או נעלם"

    js = owners[0].read_text(encoding="utf-8")
    block = js[js.index("להסיר את העסקה הקבועה?"):][:1200]

    assert "/api/recurring/" in block, "עדיין קורא למסלול שמוחק את השורה"
    assert "/api/transactions/" not in block


# ─── בידוד בין משפחות ────────────────────────────────────────────────────────

def test_a_missing_or_foreign_series_is_refused(client, monkeypatch):
    """המסלול מסנן לפי family_id; שורה שלא נמצאה חייבת להחזיר 404 ולא
    'הצלחה' על כלום."""
    c, fake = client
    monkeypatch.setattr(type(fake), "data", property(lambda self: []))

    response = c.delete(f"/api/recurring/{_TX}")

    assert response.status_code == 404


def test_the_query_is_scoped_to_the_callers_family():
    """קריאה ישירה לשכבת ה-DB — הפילטר על family_id חייב להיות שם."""
    import inspect
    src = inspect.getsource(db.stop_recurring)

    assert '.eq("family_id", family_id)' in src
