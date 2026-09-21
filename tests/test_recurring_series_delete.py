"""
מחיקת עסקה קבועה — "בטל" שיצר ₪56,000 יש מאין.

תבנית של סדרה קבועה היא שורה רגילה לכל דבר, ומופיעה ברשימת העסקאות
ככל עסקה אחרת. מחיקה ממנה נראתה תמימה, והדיאלוג אמר רק "הפעולה תסיר
את העסקה מכל הדוחות והגרפים" — אף מילה על הסדרה שמאחוריה.

בפועל המחיקה ניתקה את כל המופעים מהתבנית (‎on delete set null‎). ברגע
שהם מנותקים, המנוע כבר לא רואה שהוא יצר אותם, וגם האינדקס הייחודי
שמונע כפילות מפסיק לחול עליהם — הוא חלקי, ‎where recurring_parent_id
is not null‎. אז יצירה מחדש של אותה הוראת קבע יצרה את כל החודשים שוב.

וכפתור "בטל" עשה בדיוק את זה, אוטומטית: הוא שולח ‎is_recurring: true‎,
שמריץ מימוש מיידי. שכר דירה ₪7,000 על שמונה חודשים — ₪56,000 של הוצאה
שלא קרתה, בשתי הקשות.

אומת מול המסד החי: מחיקת תבנית השאירה ‎{'מקושרים': 0, 'יתומים': 2}‎.
"""
import pytest

from backend import app as app_module
from backend.app import app

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"
_TX  = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setattr(app_module.db, "get_transaction_receipt_path", lambda *a: None)
    # מסלול העריכה מאמת קטגוריה ובעלים לפני שהוא כותב
    monkeypatch.setattr(app_module.db, "get_categories", lambda *a, **k: [])
    monkeypatch.setattr(app_module, "family_settings",
                        lambda: dict(app_module.db.DEFAULT_FAMILY_SETTINGS))
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]   = "33333333-3333-3333-3333-333333333333"
            sess["family_id"] = _FAM
        yield c


def _series(monkeypatch, is_template, instances=0):
    monkeypatch.setattr(app_module.db, "recurring_series",
                        lambda *a: (is_template, instances))


# ─── תבנית לא נמחקת בלי בחירה מפורשת ────────────────────────────────────────

def test_deleting_a_template_asks_instead_of_deleting(client, monkeypatch):
    """הלב. עד היום זה פשוט נמחק."""
    _series(monkeypatch, True, instances=7)
    monkeypatch.setattr(app_module.db, "delete_transaction",
                        lambda *a: pytest.fail("תבנית נמחקה בלי לשאול"))

    res = client.delete(f"/api/transactions/{_TX}")

    assert res.status_code == 409
    assert res.get_json() == {"needs_choice": True, "instances": 7}


def test_the_question_carries_the_real_number(client, monkeypatch):
    """"נוצרו ממנה כבר 7 עסקאות" — מספר אמיתי, לא נוסח כללי."""
    _series(monkeypatch, True, instances=23)

    assert client.delete(f"/api/transactions/{_TX}").get_json()["instances"] == 23


def test_stopping_the_series_keeps_every_row(client, monkeypatch):
    _series(monkeypatch, True, instances=3)
    stopped = []
    monkeypatch.setattr(app_module.db, "stop_recurring",
                        lambda tx, fam: (stopped.append(tx) or (True, None)))
    monkeypatch.setattr(app_module.db, "delete_transaction",
                        lambda *a: pytest.fail("נמחק כסף בעצירת סדרה"))
    monkeypatch.setattr(app_module.db, "delete_recurring_series",
                        lambda *a: pytest.fail("נמחקה סדרה בעצירה"))

    res = client.delete(f"/api/transactions/{_TX}?mode=stop")

    assert res.status_code == 200
    assert res.get_json() == {"status": "ok", "stopped": True}
    assert stopped == [_TX]


def test_deleting_the_series_reports_how_many_went(client, monkeypatch):
    _series(monkeypatch, True, instances=3)
    monkeypatch.setattr(app_module.db, "delete_recurring_series",
                        lambda tx, fam: (4, None))

    res = client.delete(f"/api/transactions/{_TX}?mode=series")

    assert res.get_json() == {"status": "ok", "deleted": 4}


def test_an_ordinary_transaction_is_untouched(client, monkeypatch):
    """בקרת-נגד, והחשובה כאן: 99% מהמחיקות הן של עסקה רגילה, והן
    חייבות להמשיך לעבוד בדיוק כמו קודם — כולל "בטל"."""
    _series(monkeypatch, False)
    deleted = []
    monkeypatch.setattr(app_module.db, "delete_transaction",
                        lambda tx, fam: (deleted.append(tx) or True))

    res = client.delete(f"/api/transactions/{_TX}")

    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}
    assert deleted == [_TX]


def test_an_unknown_series_state_refuses_rather_than_guessing(client, monkeypatch):
    """סדרה כפולה היא נזק שאי אפשר לבטל; ניסיון חוזר לא."""
    def _boom(*a):
        raise app_module.db.DataUnavailable("recurring_series")
    monkeypatch.setattr(app_module.db, "recurring_series", _boom)
    monkeypatch.setattr(app_module.db, "delete_transaction",
                        lambda *a: pytest.fail("נמחק בלי לדעת אם יש סדרה"))

    assert client.delete(f"/api/transactions/{_TX}").status_code == 503


# ─── מופע לא יכול להפוך לתבנית שנייה ────────────────────────────────────────

def _edit(client, is_recurring):
    return client.put(f"/api/transactions/{_TX}", json={
        "amount": 100, "type": "expense", "date": "2026-09-10",
        "is_recurring": is_recurring, "recurring_frequency": "monthly_1",
    })


def test_marking_an_instance_as_recurring_is_refused(client, monkeypatch):
    """"שיהיה קבוע מעכשיו" על מופע קיים יצר סדרה שנייה שרצה במקביל
    לראשונה — אותו כסף פעמיים בחודש, לתמיד."""
    monkeypatch.setattr(app_module.db, "is_recurring_instance", lambda *a: True)
    monkeypatch.setattr(app_module.db, "update_transaction",
                        lambda *a, **k: pytest.fail("נוצרה סדרה שנייה"))

    res = _edit(client, True)

    assert res.status_code == 422
    assert "כבר חלק מסדרה קבועה" in res.get_json()["error"]


def test_an_instance_can_still_be_edited_normally(client, monkeypatch):
    """בקרת-נגד: החסימה היא על הפיכתו לתבנית, לא על עריכתו."""
    monkeypatch.setattr(app_module.db, "is_recurring_instance",
                        lambda *a: pytest.fail("נבדקה סדרה על עריכה רגילה"))
    monkeypatch.setattr(app_module.db, "update_transaction",
                        lambda *a, **k: ({"id": _TX}, None))

    assert _edit(client, False).status_code == 200


def test_an_ordinary_transaction_can_still_become_recurring(client, monkeypatch):
    """בקרת-נגד: זו התכונה עצמה — אסור לחסום אותה."""
    monkeypatch.setattr(app_module.db, "is_recurring_instance", lambda *a: False)
    monkeypatch.setattr(app_module.db, "update_transaction",
                        lambda *a, **k: ({"id": _TX}, None))
    monkeypatch.setattr(app_module.db, "materialize_recurring", lambda fam: (0, True))

    assert _edit(client, True).status_code == 200


def test_an_unknown_instance_state_refuses(client, monkeypatch):
    def _boom(*a):
        raise app_module.db.DataUnavailable("is_recurring_instance")
    monkeypatch.setattr(app_module.db, "is_recurring_instance", _boom)
    monkeypatch.setattr(app_module.db, "update_transaction",
                        lambda *a, **k: pytest.fail("נכתב בלי לדעת"))

    assert _edit(client, True).status_code == 503


# ─── סדר המחיקה בשכבת המסד ──────────────────────────────────────────────────

class _RecordingClient:
    """מתעד את סדר פעולות המחיקה, כדי לנעול אותו."""

    def __init__(self):
        self.calls = []
        self._filters = {}

    def table(self, _n):        return self
    def delete(self, *a, **k):  self._filters = {}; return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def execute(self):
        self.calls.append(dict(self._filters))
        self.data = [{"id": "x"}]
        return self


def test_the_instances_are_deleted_before_the_template(monkeypatch):
    """אם התבנית נמחקת ראשונה, המופעים מתייתמים באותו רגע — וזה בדיוק
    המצב שהפונקציה נועדה למנוע."""
    from backend import supabase_config as _db
    rec = _RecordingClient()
    monkeypatch.setattr(_db, "get_client", lambda: rec)

    _db.delete_recurring_series(_TX, _FAM)

    assert "recurring_parent_id" in rec.calls[0], "התבנית נמחקה לפני המופעים"
    assert "id" in rec.calls[1]


def test_deleting_a_missing_template_says_so(monkeypatch):
    from backend import supabase_config as _db

    class _Empty(_RecordingClient):
        def execute(self):
            super().execute()
            self.data = []
            return self

    monkeypatch.setattr(_db, "get_client", lambda: _Empty())

    assert _db.delete_recurring_series(_TX, _FAM) == (0, "not found")


# ─── מה שהמשתמש רואה ────────────────────────────────────────────────────────

def _js():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    return (root / "frontend/static/js/transactions.js").read_text(encoding="utf-8")


def test_the_dialog_stops_promising_it_is_just_one_transaction():
    """הנוסח הישן — "הפעולה תסיר את העסקה מכל הדוחות והגרפים" — היה נכון
    לעסקה רגילה ומטעה לחלוטין לתבנית של סדרה."""
    block = _js()[_js().index("function askAboutSeries("):][:1600]

    assert "זו עסקה קבועה" in block
    assert "נוצרו ממנה כבר" in block
    assert "עצור את הסדרה" in block


def test_the_safe_option_is_the_confirm_button():
    """הפעולה ההרסנית לא צריכה להיות במרחק לחיצה אחת."""
    block = _js()[_js().index("function askAboutSeries("):][:1600]

    assert "confirmText: 'עצור את הסדרה'" in block
    assert "למחוק את כל הסדרה?" in block, "המחיקה המלאה לא עוברת אישור שני"


def test_backing_out_of_either_dialog_deletes_nothing():
    """נסיגה (Escape או לחיצה בחוץ) מחזירה null. דיאלוג שני שמפרש null
    כאישור הוא בדיוק הבאג שכבר היה במחיקת פרויקט."""
    block = _js()[_js().index("function askAboutSeries("):][:1600]

    assert "if (stop === null) return;" in block
    assert "if (sure !== true) return;" in block


def test_a_stopped_series_offers_no_undo():
    """אין מה לבטל — לא נמחק כלום. ו"בטל" על סדרה שנמחקה היה משחזר
    שורה אחת מתוך עשרות, כלומר גרוע מהמחיקה."""
    js = _js()
    block = js[js.index("function sendSeriesDelete("):][:1400]

    assert "label: 'בטל'" not in block
    assert "הסדרה נעצרה" in block


def test_the_recurring_checkbox_is_locked_on_an_instance():
    js = _js()

    assert "setRecurringLock(!!tx.recurringParentId)" in js
    assert "recurringCb.disabled = locked" in js
