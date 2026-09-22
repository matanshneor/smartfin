"""חמישה תיקונים במנוע ובגבולות, שכולם התבטאו כמספר שגוי ולא כשגיאה.

**אצווה שנזרקת בשלמותה.** ‎insert‎ בודד הוא משפט אחד, אז שורה אחת
מתנגשת מגלגלת אחורה את כולן. ההנחה הייתה שההתנגשות היחידה האפשרית היא
אצווה זהה לגמרי — נכון בחפיפה מלאה, שגוי בחלקית: אם בקשה מקבילה יצרה
את המשכורת ולא את שכר הדירה, **שתיהן** נזרקו, ו-‎_sync_recurring‎ סימן
"סונכרן להיום". חודש שלם בלי שכר דירה, בלי סימן.

**ממוצע שמחולק במספר החודשים שהיה בהם משהו.** תשלום שנתי בודד (ביטוח
ביולי) הפך ל"ממוצע" של עצמו, וכל אוגוסט נראה תקין לנצח.

**גרף "12 החודשים האחרונים" בלי גבול עליון.** תשלום ששולם מראש לשנה
הבאה הופיע בו כעמודה.

**כל חבר יכול למנות את עצמו למנהל** — ברמת RLS, לא דרך האפליקציה.

**קטגוריה בלי שם ובלי סוג תקין** נכנסה למסד.
"""
import re
from pathlib import Path

import pytest

from backend import supabase_config as db

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_SRC = (_ROOT / "backend/supabase_config.py").read_text(encoding="utf-8")


def _fn(name):
    i = _SRC.index(f"def {name}(")
    return _SRC[i:_SRC.index("\ndef ", i)]


# ─── ב5: נפילה חלקית לא זורקת את כל האצווה ───────────────────────────────────

def test_a_partial_conflict_retries_the_rest_one_by_one():
    """הלב. ‎return 0, True‎ על כל התנגשות הוא "הכול כבר קיים" — טענה
    שנכונה רק כשהחפיפה מלאה."""
    body = _fn("materialize_recurring")
    conflict = body[body.index("uq_tx_recurring_occurrence"):]

    assert "for row in new_rows" in conflict, \
        "אצווה שנפלה חלקית עדיין נזרקת בשלמותה"
    # ויציאה מוקדמת לפני הלולאה מבטלת אותה לגמרי, בלי לגעת בשורה הזאת.
    assert "return 0, True" not in conflict[:conflict.index("for row in new_rows")], \
        "יש יציאה מוקדמת לפני הניסיון החוזר — הלולאה לא נגישה"


def test_the_count_reflects_what_was_actually_created():
    """אחרי נפילה חלקית ‎len(new_rows)‎ אינו מה שנוצר, והקורא משתמש
    במספר הזה כדי להחליט אם משהו קרה."""
    body = _fn("materialize_recurring")

    assert "return created, True" in body
    assert "return len(new_rows), True" not in body


def test_a_conflict_that_is_not_a_duplicate_still_raises():
    """בקרת-נגד: התעלמות מכל שגיאה בלולאה החדשה הייתה הופכת אותה
    לבליעה שקטה גרועה יותר מזו שהוחלפה."""
    body = _fn("materialize_recurring")
    loop = body[body.index("for row in new_rows"):]

    assert "raise" in loop


# ─── ב10: הממוצע הוא של שלושה חודשים ─────────────────────────────────────────

def test_the_average_divides_by_the_window_and_not_by_what_it_found():
    """חודש בלי הוצאה בקטגוריה הוא ₪0, לא חודש שלא קרה."""
    body = _fn("get_anomalies")

    assert "_HISTORY_MONTHS" in body, "הממוצע עדיין מחולק במספר החודשים שנמצאו"
    assert "/ len(past)" not in body


def test_the_window_is_one_constant_shared_by_the_query_and_the_maths():
    """שליפה של 3 חודשים עם חלוקה ב-4 (או להפך) היא מספר שגוי שאי אפשר
    לראות שהוא שגוי."""
    assert "_HISTORY_MONTHS = 3" in _SRC
    assert "month - _HISTORY_MONTHS" in _SRC


# ─── ב10: הגרף לא מציג עתיד ──────────────────────────────────────────────────

def test_the_trend_chart_has_an_upper_bound():
    body = _fn("get_monthly_trend")

    assert '.lte("date"' in body, \
        'גרף "12 החודשים האחרונים" מציג גם חודשים עתידיים'
    assert "clock.today()" in body


# ─── ב10: קטגוריה חייבת שם וסוג ──────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    from backend.app import app
    from tests._fake_db import FakeSupabase

    app.config["TESTING"] = True
    fake = FakeSupabase(categories=[])
    monkeypatch.setattr(db, "get_client", lambda: fake)
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = "me"
            sess["family_id"] = "fam"
        yield c, fake


@pytest.mark.parametrize("name", ["", "   ", None])
def test_a_category_without_a_name_is_refused(client, name):
    """‎TEXT NOT NULL‎ מקבל מחרוזת ריקה — שורה בפילוח שאי אפשר לזהות."""
    c, fake = client
    body = {"type": "expense"}
    if name is not None:
        body["name"] = name

    res = c.post("/api/categories", json=body)

    assert res.status_code == 422
    assert fake.rows("categories") == []


@pytest.mark.parametrize("type_", ["transfer", "", "EXPENSE"])
def test_a_category_with_an_unknown_type_is_refused(client, type_):
    """נעצר רק ב-CHECK של המסד וחזר כ-500, אחרי שכל מסלול אחר מאמת."""
    c, fake = client

    res = c.post("/api/categories", json={"name": "מכולת", "type": type_})

    assert res.status_code == 422
    assert fake.rows("categories") == []


# ─── ב7: העמודות שנועלות את תפקיד המנהל ──────────────────────────────────────

def test_the_family_table_only_grants_the_columns_the_app_writes():
    """כל בדיקת ‎_require_manager‎ נשענת על ‎manager_id‎. בלי הגבלת
    עמודות, RLS מתירה לכל חבר לכתוב אליה ישירות — ואז הבדיקה מגינה על
    עצמה בלבד. אומת מול המסד: ‎name‎ ו-‎settings‎ עוברים,
    ‎manager_id‎ ו-‎invite_code‎ נחסמים."""
    sql = (_ROOT / "backend/supabase/migrations"
           / "20260922150000_lock_family_columns.sql").read_text(encoding="utf-8")

    assert "revoke update on public.families from authenticated" in sql
    assert re.search(r"grant\s+update\s*\(\s*name,\s*settings\s*\)", sql)
    assert "manager_id" not in sql.split("grant  update")[1]
