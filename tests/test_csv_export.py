"""
בדיקות לייצוא CSV.

נתונים שאפשר להוציא הם נתונים שאפשר לבטוח בהם, וזו התשובה הזולה ביותר
ל"מה קורה אם ארצה לעזוב" — שאלה שמשפחה שוקלת בדיוק לפני שהיא מכניסה
לאפליקציה את הכסף שלה.

שני פרטים קובעים אם הקובץ באמת נפתח נכון, ושניהם בלתי נראים בבדיקה
ידנית מהירה: BOM בתחילת הקובץ, ו-CRLF בסוף שורה. בלי ה-BOM אקסל מפרש
UTF-8 כקידוד מקומי וכל הטקסט העברי הופך לג'יבריש — וזה נראה כמו באג
באפליקציה, לא בתוכנה שפותחת.
"""
import csv
import io as _io

import pytest

from backend import app as app_module
from backend.app import app

pytestmark = pytest.mark.unit

_ROWS = [
    {"date": "2026-09-03", "type": "expense", "amount": 240.5,
     "category_name": "מזון", "description": "סופר", "user_name": "מתן",
     "project_name": None, "is_recurring": False, "recurring_parent_id": None},
    {"date": "2026-09-05", "type": "income", "amount": 14000.0,
     "category_name": "משכורת", "description": "", "user_name": "אור",
     "project_name": None, "is_recurring": True, "recurring_parent_id": None},
    {"date": "2026-09-09", "type": "expense", "amount": 22000.0,
     "category_name": "טיסות", "description": 'כרטיסים, הלוך "ושוב"',
     "user_name": "משותף", "project_name": "טיול ליפן",
     "is_recurring": False, "recurring_parent_id": None},
]


@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setattr(app_module.db, "get_month_transactions",
                        lambda fid, y, m, settings=None, viewer_user_id=None: _ROWS)
    monkeypatch.setattr(app_module, "family_settings", lambda: {})
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"]   = "11111111-1111-1111-1111-111111111111"
            sess["family_id"] = "22222222-2222-2222-2222-222222222222"
        yield c


def _fetch(client, **params):
    return client.get("/month.csv", query_string=params or {"year": 2026, "month": 9})


# ─── מה שגורם לקובץ להיפתח נכון ──────────────────────────────────────────────

def test_the_file_starts_with_a_bom_so_hebrew_is_not_mangled(client):
    """בלי זה אקסל מציג ג'יבריש, והמשתמש מאשים את האפליקציה."""
    body = _fetch(client).get_data()

    assert body.startswith(b"\xef\xbb\xbf"), "אין BOM — הטקסט העברי יישבר באקסל"


def test_rows_end_with_crlf(client):
    body = _fetch(client).get_data()

    assert b"\r\n" in body


def test_it_is_served_as_a_download_with_a_dated_name(client):
    response = _fetch(client, year=2026, month=3)

    assert response.headers["Content-Type"].startswith("text/csv")
    assert 'filename="smartfin-2026-03.csv"' in response.headers["Content-Disposition"]


def test_it_is_never_cached(client):
    """קובץ שמכיל את כל עסקאות החודש לא אמור להישמר במטמון של proxy."""
    assert _fetch(client).headers["Cache-Control"] == "no-store"


# ─── התוכן ───────────────────────────────────────────────────────────────────

def _parse(client, **params):
    text = _fetch(client, **params).get_data(as_text=True).lstrip("﻿")
    return list(csv.reader(_io.StringIO(text)))


def test_every_transaction_appears_once_under_a_header(client):
    rows = _parse(client)

    assert rows[0][0] == "תאריך"
    assert len(rows) == 1 + len(_ROWS)


def test_the_type_is_written_in_hebrew_not_as_the_database_value(client):
    """הקובץ נפתח מול רואה חשבון, לא מול מתכנת."""
    rows = _parse(client)

    assert [r[1] for r in rows[1:]] == ["הוצאה", "הכנסה", "הוצאה"]


def test_amounts_keep_their_agorot(client):
    """‎{:,.0f}‎ בתצוגה מעגל לשקלים שלמים; בייצוא זה היה מאבד מידע."""
    rows = _parse(client)

    assert rows[1][2] == "240.50"


def test_quotes_and_commas_in_a_description_survive(client):
    """פסיק בתיאור הוא הדרך הקלאסית לשבור CSV — csv.writer מטפל, אבל
    רק אם באמת משתמשים בו ולא מחברים מחרוזות."""
    rows = _parse(client)

    assert rows[3][4] == 'כרטיסים, הלוך "ושוב"'


def test_the_project_and_recurring_columns_are_filled(client):
    rows = _parse(client)

    assert rows[3][6] == "טיול ליפן"
    assert rows[2][7] == "כן"
    assert rows[1][7] == ""


# ─── פרטיות והרשאות ──────────────────────────────────────────────────────────

def test_the_export_hides_what_the_screen_hides(client, monkeypatch):
    """אותה שליפה של עמוד החודש, כולל סינון פרויקט אישי של בן משפחה אחר.
    ייצוא שעוקף את הסינון הוא דלת אחורית לנתונים פרטיים."""
    seen = {}
    monkeypatch.setattr(app_module.db, "get_month_transactions",
                        lambda fid, y, m, settings=None, viewer_user_id=None:
                            (seen.update(viewer=viewer_user_id) or []))

    _fetch(client)

    assert seen["viewer"] == "11111111-1111-1111-1111-111111111111"


def test_it_needs_a_session():
    app.config["TESTING"] = True
    response = app.test_client().get("/month.csv")

    assert response.status_code == 302
