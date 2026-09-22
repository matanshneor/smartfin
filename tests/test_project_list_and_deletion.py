"""רשימת הפרויקטים הציגה סכום ו-✕, ושניהם היו במקום הלא נכון.

**הסכום** דורש הקשר שאין ברשימה: ₪4,200 מתוך מה? על פני כמה זמן? מול
איזה יעד? בתוך הפרויקט כל זה מוצג ממילא.

**וה-✕** היה הפעולה הבלתי הפיכה ביותר בעמוד, במרחק נגיעה אחת מהשם של
הפרויקט, בלי שום מידע על מה עומד להימחק. היא נשאלה בשתי שאלות רצופות
כי לא היה שום דבר אחר שיספר מה יאבד.

שניהם עברו לתוך הפרויקט. שם המשתמש כבר ראה את הסכומים ואת העסקאות,
ואזור המחיקה אומר במפורש כמה עסקאות עומדות על הפרק.
"""
import re
from pathlib import Path

import pytest

from backend import supabase_config as db
from backend.app import app, limiter
from tests._fake_db import FakeSupabase

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_LIST = (_ROOT / "frontend/templates/projects.html").read_text(encoding="utf-8")
_EDIT = (_ROOT / "frontend/templates/project_edit.html").read_text(encoding="utf-8")
_JS = _ROOT / "frontend/static/js"

_FAM, _ME = "f" * 8, "m" * 8


# ─── הרשימה: שמות בלבד ───────────────────────────────────────────────────────

def test_the_list_shows_no_amounts():
    """סכום בלי הקשר הוא מספר שאי אפשר לעשות איתו כלום."""
    rows = _LIST[_LIST.index('id="projectsList"'):]
    rows = rows[:rows.index("</ul>")]

    assert "project-amount" not in rows


def test_the_list_has_no_delete_button():
    """✕ ליד השם, בלי לדעת מה יימחק."""
    assert "delete-project-btn" not in _LIST


def test_nothing_still_listens_for_that_button():
    """מאזין יתום הוא באג שממתין למי שיחזיר את ה-HTML."""
    owners = [f.name for f in _JS.glob("*.js")
              if "closest('.delete-project-btn')" in f.read_text(encoding="utf-8")]

    assert owners == [], f"עדיין יש מאזין ב: {owners}"


def test_the_row_still_says_it_can_be_opened():
    """שורה בלי סכום היא שורה בלי משקל מימין — בלי סימן, היא נראית
    כמו טקסט ולא כמו כניסה."""
    assert "project-chevron" in _LIST
    assert "project_detail" in _LIST


def test_the_name_and_description_survived():
    """בקרת-נגד: הורדנו סכום ומחיקה, לא את התוכן."""
    assert "project-name" in _LIST
    assert "p.description" in _LIST


# ─── בתוך הפרויקט: הסכום והמחיקה ─────────────────────────────────────────────

def test_the_project_page_still_shows_the_totals():
    """זה המקום שאליו הסכום עבר."""
    detail = (_ROOT / "frontend/templates/project_detail.html").read_text(encoding="utf-8")

    assert "hero-totals" in detail
    assert "project.spent" in detail


def test_deletion_lives_in_the_projects_own_management():
    assert "project-danger" in _EDIT
    assert 'id="confirmDeleteProjectBtn"' in _EDIT


def test_it_says_how_many_transactions_will_be_affected():
    """✕ ברשימה לא נשא שום מספר."""
    block = _EDIT[_EDIT.index("project-danger"):]

    assert "tx_count" in block
    assert "אין לפרויקט עסקאות" in block, "פרויקט ריק מקבל ניסוח משלו"


def test_the_default_keeps_the_money():
    """מחיקת פרויקט אינה מחיקת ההוצאות שנרשמו בו — הן קרו."""
    block = _EDIT[_EDIT.index("project-danger"):]
    active = re.search(r'class="toggle-btn active" data-tx-mode="(\w+)"', block)

    assert active and active.group(1) == "keep"

    js = (_JS / "project-edit.js").read_text(encoding="utf-8")
    assert "let txMode = 'keep';" in js, "ה-JS מתחיל ממצב אחר מהסימון החזותי"


def test_choosing_to_delete_changes_what_the_hint_says():
    """בלי זה הבחירה נראית כמו העדפה ולא כמו החלטה על כסף."""
    js = (_JS / "project-edit.js").read_text(encoding="utf-8")

    assert "projectTxModeHint" in js
    assert "לא יופיעו בשום דוח" in js


# ─── ושהמסלול באמת עושה את שתי הפעולות ───────────────────────────────────────

@pytest.fixture
def project(monkeypatch):
    limiter.reset()
    app.config["TESTING"] = True
    fake = FakeSupabase(
        projects=[{"id": "p1", "family_id": _FAM, "name": "שיפוץ", "owner_id": None,
                   "archived": False, "track_expense": True,
                   "track_income": False, "track_savings": False}],
        transactions=[{"id": f"t{i}", "family_id": _FAM, "project_id": "p1",
                       "amount": 100.0, "type": "expense", "date": "2026-09-01"}
                      for i in range(3)],
    )
    monkeypatch.setattr(db, "get_client", lambda: fake)
    monkeypatch.setattr(db, "get_project_for_transaction",
                        lambda pid, fid: {"id": pid, "owner_id": None,
                                          "track_expense": True, "track_income": False,
                                          "track_savings": False})
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = _ME
            sess["family_id"] = _FAM
        yield c, fake


def test_keeping_the_transactions_leaves_every_one_of_them(project):
    c, fake = project

    res = c.delete("/api/projects/p1", json={"delete_transactions": False})

    assert res.status_code == 200
    assert res.get_json()["deleted"] == 0
    assert len(fake.rows("transactions")) == 3, "עסקאות נמחקו למרות הבחירה"
    assert fake.rows("projects") == []


def test_deleting_them_reports_the_real_number(project):
    """המספר מגיע מהשרת ולא מהדפדפן — אחרת הוא הבטחה שלא נבדקה."""
    c, fake = project

    res = c.delete("/api/projects/p1", json={"delete_transactions": True})

    assert res.get_json()["deleted"] == 3
    assert fake.rows("transactions") == []
