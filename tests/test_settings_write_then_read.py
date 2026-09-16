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
