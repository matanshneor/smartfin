"""קישור לפרויקט שנמחק מוביל לרשימת הפרויקטים, לא לדף תקלה.

‎.single()‎ על אפס שורות זורק, והחריגה הפכה ל-‎DataUnavailable‎: "לא
הצלחנו לטעון את הנתונים, נסו לרענן" — על פרויקט שפשוט לא קיים, ורענון
לא יעזור לעולם. זה קרה לכל מי שהיה על המסך של פרויקט שבן משפחה מחק,
או חזר אחורה בדפדפן לפרויקט שמחק בעצמו.
"""
import pytest

from backend import supabase_config as db
from backend.app import app, limiter

from tests._fake_db import FakeSupabase

pytestmark = pytest.mark.unit

_FAM  = "11111111-1111-1111-1111-111111111111"
_ME   = "22222222-2222-2222-2222-222222222222"
_GONE = "44444444-4444-4444-4444-444444444444"


def test_a_project_that_is_gone_is_none_not_a_failure(monkeypatch):
    monkeypatch.setattr(db, "get_client", lambda: FakeSupabase(projects=[], transactions=[]))

    assert db.get_project_detail(_GONE, _FAM, _ME) is None


def test_a_malformed_id_is_not_sent_to_the_database(monkeypatch):
    """PostgREST דוחה מזהה שאינו UUID בשגיאה, וזו הייתה הופכת ל-503."""
    fake = FakeSupabase(projects=[])
    monkeypatch.setattr(db, "get_client", lambda: fake)

    assert db.get_project_detail("abc", _FAM, _ME) is None
    assert fake.reads == []


def test_a_real_failure_is_still_a_failure(monkeypatch):
    """בקרת-נגד: "לא נמצא" אינו "לא הצלחנו לבדוק"."""
    class Down:
        def table(self, _):
            raise ConnectionError("down")
    monkeypatch.setattr(db, "get_client", lambda: Down())

    with pytest.raises(db.DataUnavailable):
        db.get_project_detail(_GONE, _FAM, _ME)


@pytest.fixture
def client(monkeypatch):
    limiter.reset()
    app.config["TESTING"] = True
    monkeypatch.setattr(db, "set_auth_token", lambda t: None)
    monkeypatch.setattr(db, "get_project_detail", lambda *a: None)
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = _ME
            sess["family_id"] = _FAM
        yield c


@pytest.mark.parametrize("path", [f"/projects/{_GONE}", f"/projects/{_GONE}/edit"],
                         ids=["view", "edit"])
def test_the_page_goes_to_the_list_and_says_why(client, path):
    r = client.get(path)

    assert r.status_code == 302 and r.headers["Location"].endswith("/projects")
    with client.session_transaction() as sess:
        assert sess["sf_notice"] == "הפרויקט הזה כבר לא קיים"
