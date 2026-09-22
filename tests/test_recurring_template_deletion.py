"""מחיקת המופע הראשון בסדרה הרסה את כל הסדרה, והמסך אמר את ההפך.

‎recurring_parent_id‎ הוא ‎on delete set null‎. כשהשורה שנמחקה הייתה
התבנית — והיא תמיד התבנית כשמוחקים את החודש שבו הסדרה נפתחה — כל
המופעים שנוצרו ממנה איבדו את הקישור בבת אחת:

- הסדרה הפסיקה לייצר מופעים חדשים (אין יותר שכר דירה מהחודש הבא)
- כל מה שכבר נוצר נעלם מ"עסקאות קבועות" ומהפאנל בעמוד החודש
- הדילוג נרשם על השורה שנמחקה, כלומר אבד

ובאותו רגע הממשק הודיע: **"העסקה נמחקה. שאר הסדרה נשארה"**.

ההבחנה בין "תבנית" למופע היא פנימית לגמרי, ולמי שמוחק את שכר הדירה של
מרץ לא אמור להיות אכפת שמרץ הוא במקרה החודש שבו הסדרה נפתחה. אז מחיקת
התבנית מעבירה את התפקיד למופע הבא.

אומת מול המסד החי ב-‎rollback‎: תבנית + 2 מופעים, מחיקת התבנית ב"רק את
זו" → תבנית חדשה (אפריל), מופע מקושר אחד, **0 יתומים**. לפני התיקון:
0 תבניות, 2 יתומים.
"""
from pathlib import Path

import pytest

from backend import supabase_config as db

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_MIGRATIONS = _ROOT / "backend/supabase/migrations"
_SQL = (_MIGRATIONS / "20260922120000_delete_recurring_occurrence.sql").read_text(encoding="utf-8")


class _Rpc:
    def __init__(self, result):
        self._result = result

    def execute(self):
        if isinstance(self._result, Exception):
            raise self._result
        return type("R", (), {"data": self._result})()


class _Client:
    """כפיל שמתעד את הקריאות, כדי שאפשר יהיה לבדוק **איך** נמחק."""

    def __init__(self, rpc_result=1):
        self.rpcs = []
        self.tables = []
        self._rpc_result = rpc_result

    def rpc(self, name, params=None):
        self.rpcs.append((name, dict(params or {})))
        return _Rpc(self._rpc_result)

    def table(self, name):
        self.tables.append(name)
        raise AssertionError(
            f"המחיקה נגעה ישירות בטבלה {name!r}. שלוש קריאות נפרדות הן "
            f"בדיוק מה שאפשר גם את הייתום וגם את מרוץ הדילוגים."
        )


@pytest.fixture
def client(monkeypatch):
    c = _Client()
    monkeypatch.setattr(db, "get_client", lambda: c)
    return c


# ═══ המחיקה עוברת דרך המסד, בפעולה אחת ═══════════════════════════════════════

def test_deleting_an_occurrence_is_one_atomic_call(client):
    """הלב. קודם זה היה: קרא דילוגים → כתוב דילוגים → מחק. שלוש קריאות
    שאפשר להפסיק באמצע, ושני בני משפחה יכולים לשזור."""
    ok, err = db.delete_one_occurrence("tx-1", "tpl-1", "2026-03-01", "fam-1")

    assert ok and err is None
    assert [name for name, _ in client.rpcs] == ["delete_recurring_occurrence"]
    assert client.tables == [], "משהו עדיין נגע בטבלה ישירות"


def test_the_row_identifies_itself_to_the_database(client):
    """התבנית והתאריך נגזרים מהשורה בתוך המסד, לא נשלחים מכאן — אחרת
    אפשר למחוק שורה אחת ולרשום דילוג על אחרת."""
    db.delete_one_occurrence("tx-1", "tpl-1", "2026-03-01", "fam-1")

    _, params = client.rpcs[0]
    assert params == {"p_tx_id": "tx-1", "p_family_id": "fam-1"}


def test_deleting_nothing_is_reported_as_not_found(monkeypatch):
    """שורה שבן משפחה אחר כבר מחק חייבת להיאמר, לא להיבלע כהצלחה."""
    monkeypatch.setattr(db, "get_client", lambda: _Client(rpc_result=0))

    ok, err = db.delete_one_occurrence("tx-נעלם", "tpl-1", "2026-03-01", "fam-1")

    assert ok is False
    assert err == "not found"


def test_a_database_failure_is_not_reported_as_success(monkeypatch):
    monkeypatch.setattr(db, "get_client",
                        lambda: _Client(rpc_result=RuntimeError("boom")))

    ok, err = db.delete_one_occurrence("tx-1", "tpl-1", "2026-03-01", "fam-1")

    assert ok is False and err


# ═══ מה שהפונקציה במסד מבטיחה ════════════════════════════════════════════════

def test_the_migration_promotes_an_heir_instead_of_orphaning_the_series():
    """זה התיקון עצמו. בלי ההעברה, מחיקת התבנית מנתקת כל מופע שנוצר
    ממנה — וזה קורה בכל פעם שמוחקים את החודש הראשון."""
    assert "recurring_parent_id = v_heir.id" in _SQL, \
        "האחים לא מועברים ליורש — הם יתייתמו ברגע שהתבנית נמחקת"
    assert "is_recurring        = true" in _SQL, \
        "היורש לא הופך לתבנית, כלומר הסדרה מפסיקה לייצר מופעים"


def test_the_heir_carries_what_defines_the_series():
    """יורש בלי תדירות הוא תבנית שלא תייצר כלום, ויורש בלי תאריך סיום
    הוא סדרה שלא תסתיים לעולם."""
    for field in ("recurring_frequency", "recurring_end_date", "recurring_skips"):
        assert f"{field}" in _SQL.split("v_heir.id")[0], f"{field} לא עובר ליורש"


def test_the_skip_is_recorded_before_anything_in_the_series_is_deleted():
    """בסדר ההפוך, כשל בכתיבה משאיר מופע מחוק בלי סימן — והוא חוזר מחר.

    נמדד על נתיב הסדרה בלבד: שורה שאין לה תבנית נמחקת מוקדם יותר בכוונה,
    כי אין שם שום סדרה לרשום עליה דילוג."""
    series = _SQL[_SQL.index("v_template is null"):]
    series = series[series.index("end if;"):]      # אחרי הענף חסר-התבנית

    skip_at = series.index("set recurring_skips")
    deletes = [i for i in range(len(series))
               if series.startswith("delete from public.transactions", i)]

    assert deletes, "אין בכלל מחיקה בנתיב הסדרה"
    assert skip_at < min(deletes), "מוחקים לפני שהדילוג נרשם"


def test_the_function_does_not_trust_the_family_id_it_is_given():
    """‎security definer‎ עוקף RLS. בלי הבדיקה המפורשת, כל משתמש מחובר
    יכול למחוק עסקה של כל משפחה אחרת בעולם."""
    assert "auth.uid()" in _SQL
    assert "security definer" in _SQL


def test_the_function_is_not_callable_by_anonymous_visitors():
    assert "revoke all on function public.delete_recurring_occurrence" in _SQL
    assert "to authenticated" in _SQL
