"""
בדיקות לקריאה שבאה מיד אחרי כתיבה, באותה בקשה.

יש מטמון-לבקשה שמונע שליפה חוזרת של אותם נתונים. update_family_settings
שולף את ההגדרות הקיימות כדי למזג לתוכן עדכון חלקי — והשליפה הזאת לבדה
ממלאת את המטמון בערך **שלפני** הכתיבה. המסלול מחזיר אחר כך את ההגדרות
באותה בקשה, ומקבל מהמטמון את הישנות.

הנזק לא נעצר בתצוגה: settings.js שומר את התשובה ומשתמש בה כדי להחליט
אם להציג את בורר בן המשפחה במודאל העסקה. מי שהדליק "שיוך הוצאות" קיבל
תשובה שאומרת שזה כבוי, המודאל לא הציג בורר, והשרת — שקורא בבקשה הבאה
את הערך הטרי — שייך כל עסקה למי שמחובר. שיוך שקט ושגוי של כסף, עד
הרענון הבא.
"""
from pathlib import Path

import pytest
from flask import g

from backend import supabase_config as db
from backend.app import app

pytestmark = pytest.mark.unit

_FAM = "11111111-1111-1111-1111-111111111111"


class _FakeFamilies:
    """שורת משפחה אחת בזיכרון, שמשקפת כתיבות מיד."""

    def __init__(self):
        self.row = {"id": _FAM, "name": "שניאור",
                    "settings": {"owner_attribution": {"expense": False}}}
        self.reads = 0
        self._pending = None

    def table(self, _n):            return self

    def rpc(self, name, params=None):
        """המיזוג עבר למסד, לתוך משפט אחד עם ‎for update‎ — כי קרא-מזג-כתוב
        מפייתון אפשר לשני בני משפחה לדרוס זה את זה. הכפיל מחקה את אותה
        סמנטיקה, אחרת הבדיקה מאמתת את עצמה ולא את הקוד."""
        assert name == "merge_family_settings", name
        merged = dict(self.row.get("settings") or {})
        whole = set(params.get("p_whole_keys") or [])
        for k, v in (params.get("p_patch") or {}).items():
            if k not in whole and isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = {**merged[k], **v}
            else:
                merged[k] = v
        self._pending = {"settings": merged}
        return self
    def select(self, *a, **k):      return self
    def eq(self, *a, **k):          return self
    def single(self, *a, **k):      return self
    def update(self, payload, **k): self._pending = payload; return self
    def maybe_single(self, *a, **k): return self

    def execute(self):
        if self._pending is not None:
            self.row.update(self._pending)
            self._pending = None
        else:
            self.reads += 1
        return self

    @property
    def data(self):                 return dict(self.row)


@pytest.fixture
def fake(monkeypatch):
    client = _FakeFamilies()
    monkeypatch.setattr(db, "get_client", lambda: client)
    return client


def test_reading_settings_after_writing_them_returns_the_new_value(fake):
    """הלב: אותה בקשה, כתיבה ואז קריאה."""
    with app.test_request_context("/"):
        db.update_family_settings(_FAM, {"owner_attribution": {"expense": True}})

        after = db.get_family_settings(_FAM)

    assert after["owner_attribution"]["expense"] is True, (
        "הוחזר הערך שלפני השמירה — הדפדפן יאמין לו ויוסיף עסקאות עם שיוך הפוך"
    )


def test_renaming_the_family_is_visible_in_the_same_request(fake):
    with app.test_request_context("/"):
        db.get_family(_FAM)                       # ממלא את המטמון
        db.update_family_name(_FAM, "משפחת כהן")

        assert db.get_family(_FAM)["name"] == "משפחת כהן"


def test_both_caches_are_cleared_not_just_one(fake):
    """app.py מחזיק עותק נוסף על g.family_settings. פינוי של אחד בלבד
    משאיר את הערך הישן בדיוק במקום שממנו הוא מוגש לתבניות."""
    with app.test_request_context("/"):
        g.family_settings = {"owner_attribution": {"expense": False}}
        g._sf_cache = {f"family:{_FAM}": {"settings": {}}}

        db.update_family_settings(_FAM, {"owner_attribution": {"expense": True}})

        assert "family_settings" not in g
        assert f"family:{_FAM}" not in g._sf_cache


def test_the_cache_still_does_its_job_when_nothing_was_written(fake):
    """בקרת-נגד: הפינוי לא אמור לבטל את המטמון עצמו, אחרת כל עמוד
    חוזר לשלוף את אותה שורה שלוש-ארבע פעמים."""
    with app.test_request_context("/"):
        db.get_family(_FAM)
        db.get_family(_FAM)
        db.get_family(_FAM)

    assert fake.reads == 1, f"השורה נשלפה {fake.reads} פעמים במקום אחת"


# ─── המיזוג עבר למסד, ושתי הגרסאות חייבות להסכים ────────────────────────────
#
# קרא-מזג-כתוב מפייתון אפשר לשני בני משפחה לדרוס זה את זה: אמא קובעת
# תקציב ב-20:00:00.1, אבא מכבה שיוך ב-20:00:00.3, שניהם קראו את אותו
# JSON — והכתיבה של אבא נושאת את ‎limits‎ מלפני אמא ומוחקת את התקציב
# שלה. שניהם קיבלו "נשמר".
#
# המיזוג עכשיו במשפט אחד עם ‎for update‎. שתי הסמנטיקות נשארות בקוד
# (פייתון ל-‎get_family_settings‎, SQL לכתיבה), אז הן יכולות להיפרד
# בשקט — והבדיקות כאן לא נותנות.

_MERGE_SQL = (Path(__file__).resolve().parent.parent /
              "backend/supabase/migrations/20260922140000_atomic_settings_merge.sql"
              ).read_text(encoding="utf-8")


def test_the_write_path_no_longer_merges_in_python():
    """הלב: אם המיזוג חזר לכאן, גם המרוץ חזר."""
    src = (Path(__file__).resolve().parent.parent /
           "backend/supabase_config.py").read_text(encoding="utf-8")
    block = src[src.index("def update_family_settings("):]
    block = block[:block.index("\n\ndef ")]

    assert "merge_family_settings" in block, "הכתיבה לא עוברת בפונקציית המסד"
    assert "_merge_settings(" not in block, "המיזוג חזר לפייתון — ואיתו המרוץ"


def test_the_database_locks_the_row_while_it_merges():
    """בלי ‎for update‎ הפונקציה היא בדיוק אותו קרא-מזג-כתוב, רק בשפה
    אחרת: הקורא השני עדיין קורא את הערך שלפני הראשון."""
    assert "for update" in _MERGE_SQL


def test_the_whole_map_keys_travel_with_the_patch():
    """‎limits‎ חייב להיות מוחלף ולא ממוזג — הסרת תקציב מיוצגת בהיעדרו
    מהמפה, ומיזוג לא יכול לבטא היעדר. הרשימה נשלחת מפייתון כדי ששני
    המימושים לא יחזיקו עותק משלהם."""
    src = (Path(__file__).resolve().parent.parent /
           "backend/supabase_config.py").read_text(encoding="utf-8")

    assert "p_whole_keys" in src
    assert "sorted(_WHOLE_MAP_KEYS)" in src, \
        "רשימת המפתחות מקודדת פעמיים — שתי הגרסאות יתפצלו"


def test_the_function_checks_membership_itself():
    """‎security definer‎ עוקף RLS. בלי הבדיקה, כל משתמש מחובר יכול
    לכתוב הגדרות לכל משפחה בעולם — כולל לאן משויך הכסף."""
    assert "not a member of that family" in _MERGE_SQL
    assert "auth.uid()" in _MERGE_SQL
