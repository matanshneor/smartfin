"""
בדיקות לזרימת ההצטרפות למשפחה.

זה המסלול שנשבר בשקט מאז שנכתב: join_family_by_code בדק שהמשפחה קיימת
ב-SELECT רגיל, ומדיניות ה-RLS families_member_read מתירה לקרוא משפחה רק
למי שכבר חבר בה — כלומר לעולם לא למצטרף. הבדיקה תמיד חזרה ריקה, הפונקציה
החזירה False, והערך נזרק. בלי כיסוי אוטומטי אין שום דבר שימנע רגרסיה
שקטה נוספת.

רצות מול הפרויקט האמיתי (כמו test_rls_isolation) עם שני חשבונות הבדיקה
הקבועים. כל בדיקה שמזיזה משתמש בין משפחות מחזירה אותו למקומו ב-finally,
גם אם היא נכשלת.
"""
import json
import re
import subprocess
import uuid
from pathlib import Path

import pytest

from backend import supabase_config as db

_BACKEND = Path(__file__).resolve().parent.parent / "backend"


def _privileged(sql: str):
    """מריצה SQL בהרשאות בעלים, דרך ה-CLI המקושר.

    נדרש להקמת המצב בלבד. מאז מיגרציה 20260916100000 סשן מאומת לא יכול
    ליצור משפחה או לשנות את השיוך של עצמו — זו בדיוק ההגנה שנוספה, והיא
    מה שמנעה ממשתמש להעביר את עצמו למשפחה אחרת ולקרוא את הכספים שלה.
    הבדיקות האלה צריכות בכל זאת להעמיד משפחה זמנית, ולכן הן עושות את זה
    מחוץ למודל ההרשאות של האפליקציה במקום להחליש אותו.

    מה שנבדק — join_family_by_code — רץ כרגיל דרך הלקוח המאומת."""
    out = subprocess.run(
        ["supabase", "db", "query", sql, "--linked"],
        cwd=_BACKEND, capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"הקמת מצב נכשלה: {out.stderr[:300]}")
    return out.stdout


def _profile_family(user_id):
    profile = db.get_profile(user_id)
    return profile.get("family_id") if profile else None


def _dispose_temp_family(client, user_id, temp_id, home_code):
    """מוחקת משפחה זמנית ומחזירה את המשתמש הביתה.

    אין מדיניות DELETE על families, כך שלקוח לא יכול למחוק משפחה ישירות —
    ניקוי המשפחה הנטושה בתוך join_family_by_code הוא הדרך היחידה. לכן
    מעמידים את המשתמש במשפחה, מרוקנים אותה מתנועות, ומצרפים אותו הביתה
    בקוד: ה-RPC עצמו מוחק אותה בדרך החוצה.

    הסדר כאן קריטי: ה-RLS על transactions מתיר מחיקה רק בתוך המשפחה של
    המשתמש, אז המעבר חייב לקרות לפני המחיקה — אחרת היא נכשלת בשקט
    והמשפחה שורדת עם תנועה יתומה."""
    _privileged(f"update public.profiles set family_id='{temp_id}' where id='{user_id}';")
    client.table("transactions").delete().eq("family_id", temp_id).execute()
    db.join_family_by_code(home_code)


@pytest.fixture
def family_a_code(family_a):
    """קוד ההזמנה של משפחה א'. חבר במשפחה רשאי לקרוא אותה, אז שליפה רגילה
    מספיקה כאן."""
    family = db.get_family(family_a["family_id"])
    code = family.get("invite_code")
    assert code, "למשפחת הבדיקה אין קוד הזמנה — האם המיגרציה הוחלה?"
    return code


# ─── תצוגה מקדימה ────────────────────────────────────────────────────────────

def test_preview_returns_the_family_name(family_a, family_a_code):
    expected = db.get_family(family_a["family_id"]).get("name")

    assert db.family_name_for_code(family_a_code) == expected


@pytest.mark.parametrize("mangle", [
    lambda c: c.lower(),                        # אותיות קטנות
    lambda c: f"  {c}  ",                       # רווחים מסביב
    lambda c: f"{c[:3]}-{c[3:]}",               # מקף באמצע
    lambda c: f" {c[:3].lower()}-{c[3:]} ",     # הכל ביחד
])
def test_preview_normalizes_a_mangled_code(family_a_code, mangle):
    """הקוד עובר בוואטסאפ ובהקראה בטלפון — רווחים, מקפים ואותיות קטנות
    הם המצב הרגיל ולא חריג."""
    expected = db.family_name_for_code(family_a_code)

    assert db.family_name_for_code(mangle(family_a_code)) == expected


def test_preview_returns_none_for_an_unknown_code():
    assert db.family_name_for_code("ZZZZZZ") is None


def test_preview_returns_none_for_an_empty_code():
    assert db.family_name_for_code("") is None


# ─── דחיית קודים שגויים ──────────────────────────────────────────────────────

def test_join_rejects_an_unknown_code(family_a):
    before = _profile_family(family_a["user_id"])

    family_id, err = db.join_family_by_code("ZZZZZZ")

    assert family_id is None
    assert err, "קוד שגוי חייב להחזיר שגיאה — הבליעה השקטה היא כל הבאג"
    assert _profile_family(family_a["user_id"]) == before, "כישלון לא אמור להזיז אף אחד"


def test_join_rejects_an_empty_code(family_a):
    family_id, err = db.join_family_by_code("   ")

    assert family_id is None
    assert err


def test_join_is_idempotent_for_the_family_you_are_already_in(family_a, family_a_code):
    """הצטרפות למשפחה שאתה כבר חבר בה לא אמורה לשנות דבר — ובעיקר לא
    להפעיל את ניקוי המשפחה הנטושה על המשפחה של עצמך."""
    family_id, err = db.join_family_by_code(family_a_code)

    assert err is None
    assert family_id == family_a["family_id"]
    assert _profile_family(family_a["user_id"]) == family_a["family_id"]


# ─── ההצטרפות עצמה + ניקוי המשפחה הנטושה ─────────────────────────────────────

def test_join_moves_the_user_and_deletes_the_family_left_behind(family_a, family_a_code):
    """המסלול המלא, ובתוכו הסעיף שמונע הצטברות זבל.

    בכניסה הראשונה ensure_family פותח לכל משתמש משפחה משלו, כך שמצטרף תמיד
    נוטש משפחה ריקה. בלי הניקוי כל הצטרפות מוצלחת הייתה משאירה עוד שורת
    "המשפחה שלי" יתומה — בדיוק מה שהצטבר בטבלה עד היום.

    כדי לבדוק את זה בלי לסכן את משפחת הבדיקה עצמה, מקימים משפחה זמנית,
    מעבירים אליה את המשתמש ישירות (לא דרך ה-RPC), ואז מצרפים אותו חזרה
    בקוד — כך שהמשפחה שנוטשת ונמחקת היא הזמנית ולא האמיתית."""
    client    = db.get_client()
    temp_id   = str(uuid.uuid4())
    temp_code = "TST" + uuid.uuid4().hex[:3].upper()
    original  = family_a["family_id"]

    _privileged(f"insert into public.families(id,name,invite_code) "
                f"values ('{temp_id}','משפחה זמנית לבדיקה','{temp_code}');")

    try:
        # מעבירים ישירות, כדי שהמעבר-בחזרה יהיה זה שנבדק
        _privileged(f"update public.profiles set family_id='{temp_id}' "
                    f"where id='{family_a['user_id']}';")
        assert _profile_family(family_a["user_id"]) == temp_id

        family_id, err = db.join_family_by_code(family_a_code)

        assert err is None, f"ההצטרפות נכשלה: {err}"
        assert family_id == original
        assert _profile_family(family_a["user_id"]) == original

        # המשפחה הזמנית נותרה בלי חברים ובלי תנועות, ולכן אמורה להימחק.
        # בודקים דרך ה-RPC ולא ב-SELECT: אחרי המעבר אין למשתמש הרשאת קריאה
        # על המשפחה הזמנית, אבל family_name_for_code הוא security definer.
        assert db.family_name_for_code(temp_code) is None, \
            "המשפחה הנטושה לא נמחקה — כל הצטרפות תשאיר מעכשיו שורת זבל"
    finally:
        # משחזרים גם אם נפלנו באמצע, כדי לא להשאיר את חשבון הבדיקה תלוי באוויר.
        # אם ה-RPC כבר מחק את המשפחה הזמנית — הניקוי הזה פשוט לא ימצא מה לעשות.
        if db.family_name_for_code(temp_code) is not None:
            _dispose_temp_family(client, family_a["user_id"], temp_id, family_a_code)
        _privileged(f"update public.profiles set family_id='{original}' "
                    f"where id='{family_a['user_id']}';")


def test_join_keeps_a_family_that_still_holds_transactions(family_a, family_a_code):
    """בקרת-נגד לניקוי: משפחה שיש בה היסטוריה לא נמחקת גם כשהחבר האחרון עוזב.

    זה הסעיף שמפריד בין "ניקוי זבל" ל"איבוד נתונים", ולכן חייב כיסוי משלו.
    שוב דרך משפחה זמנית — הפעם כזו שמחזיקה תנועה אחת."""
    client    = db.get_client()
    temp_id   = str(uuid.uuid4())
    temp_code = "TST" + uuid.uuid4().hex[:3].upper()
    original  = family_a["family_id"]

    _privileged(f"insert into public.families(id,name,invite_code) "
                f"values ('{temp_id}','משפחה זמנית עם היסטוריה','{temp_code}');")

    try:
        _privileged(f"update public.profiles set family_id='{temp_id}' "
                    f"where id='{family_a['user_id']}';")

        client.table("transactions").insert(
            {"family_id": temp_id, "amount": 1, "type": "expense",
             "date": "2026-01-01", "description": "join test"},
            returning="minimal",
        ).execute()

        family_id, err = db.join_family_by_code(family_a_code)

        assert err is None
        assert family_id == original
        assert db.family_name_for_code(temp_code) is not None, \
            "משפחה עם תנועות נמחקה — זה איבוד נתונים, לא ניקוי"
    finally:
        _dispose_temp_family(client, family_a["user_id"], temp_id, family_a_code)
        _privileged(f"update public.profiles set family_id='{original}' "
                    f"where id='{family_a['user_id']}';")
