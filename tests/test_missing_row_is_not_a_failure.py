"""שורה שלא קיימת היא "אין", לא "לא הצלחנו לבדוק".

ב-postgrest-py שלנו ‎.maybe_single().execute()‎ מחזיר ‎None‎ כשאין שורה,
ו-‎.execute().data‎ זרק. ארבע פונקציות הפכו כך עסקה שנמחקה רגע קודם
לתקלה — הבולטת: מחיקה של עסקה שבן משפחה אחר כבר מחק ענתה "לא הצלחנו
לבדוק אם זו עסקה קבועה — נסו שוב". (נמצא בבדיקת דפדפן; הכפיל החזיר
תשובה ריקה "מנומסת" והסתיר את זה, ועכשיו הוא מתנהג כמו האמיתי.)
"""
import pytest

from backend import supabase_config as db

from tests._fake_db import FakeSupabase

pytestmark = pytest.mark.unit

_FAM  = "11111111-1111-1111-1111-111111111111"
_GONE = "44444444-4444-4444-4444-444444444444"


@pytest.fixture
def empty(monkeypatch):
    fake = FakeSupabase(transactions=[])
    monkeypatch.setattr(db, "get_client", lambda: fake)
    return fake


def test_a_gone_transaction_is_not_part_of_a_series(empty):
    assert db.recurring_occurrence(_GONE, _FAM) == (None, True)


def test_a_gone_transaction_has_no_type(empty):
    assert db.transaction_type(_GONE, _FAM) is None


def test_a_gone_transaction_is_not_an_instance(empty):
    assert db.is_recurring_instance(_GONE, _FAM) is False


def test_stopping_a_series_whose_template_is_gone(empty):
    assert db.delete_occurrences_from(_GONE, "2026-09-01", _FAM) == (0, None)


def test_the_fake_behaves_like_postgrest(empty):
    """בלי זה הבדיקות למעלה היו עוברות גם על הקוד הישן."""
    assert empty.table("transactions").select("id").eq("id", _GONE).maybe_single().execute() is None
