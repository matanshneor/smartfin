"""
מחיקת עסקה שחוזרת — השאלה של יומן.

מתן ניסח את המודל: "כל עסקה קבועה שאני מוחק צריך לשאול אותי אם למחוק
את כל המופעים מכאן והלאה או רק את המופע הנוכחי. לא צריך להיות הבדל
בין עסקה קבועה מקורית לבין מופע שלה."

הוא צודק. ההבחנה בין "תבנית" למופע היא פנימית לגמרי — שורת התבנית
היא עסקה רגילה שבמקרה גם מגדירה את הסדרה — ולמי שמוחק את שכר הדירה
של מרץ לא אמור להיות אכפת אם מרץ הוא במקרה החודש שבו הסדרה נפתחה.

הגרסה הקודמת שאלה "לעצור או למחוק הכול", ורק על שורת התבנית. במקרה
של מתן כל חמש התבניות מיולי, אז מדשבורד ספטמבר אי אפשר היה להגיע
לשאלה בכלל — הוא ניסה, לא קרה כלום, ודיווח שזה לא עובד.

"רק את זו" דורש שהמנוע יזכור שדילגו: הוא מחליט מה חסר לפי מה שקיים,
אז מופע שנמחק נראה לו כמו חודש שעוד לא נוצר — והוא משלים אותו למחרת.
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


def _occurrence(monkeypatch, info):
    monkeypatch.setattr(app_module.db, "recurring_occurrence", lambda *a: (info, True))


_SERIES = {"template_id": "tpl-1", "date": "2026-09-01", "later": 4}


# ─── אין הבדל בין "מקורית" למופע ────────────────────────────────────────────

def test_any_recurring_transaction_asks_the_same_question(client, monkeypatch):
    """הלב של מה שמתן ביקש. קודם רק שורת התבנית שאלה, וכל המופעים
    נמחקו בשקט."""
    _occurrence(monkeypatch, _SERIES)
    monkeypatch.setattr(app_module.db, "delete_transaction",
                        lambda *a: pytest.fail("נמחק בלי לשאול"))

    res = client.delete(f"/api/transactions/{_TX}")

    assert res.status_code == 409
    assert res.get_json() == {"needs_choice": True, "later": 4}


def test_the_question_carries_the_real_number(client, monkeypatch):
    _occurrence(monkeypatch, dict(_SERIES, later=23))

    assert client.delete(f"/api/transactions/{_TX}").get_json()["later"] == 23


# ─── "רק את זו" ─────────────────────────────────────────────────────────────

def test_deleting_one_occurrence_records_the_skip(client, monkeypatch):
    """בלי הרישום המנוע משלים את החודש הזה מחדש למחרת, והמחיקה
    מתבטלת מעצמה."""
    called = []
    _occurrence(monkeypatch, _SERIES)
    monkeypatch.setattr(app_module.db, "delete_one_occurrence",
                        lambda tx, tpl, d, fam: (called.append((tx, tpl, d)) or (True, None)))

    res = client.delete(f"/api/transactions/{_TX}?mode=one")

    assert res.get_json() == {"status": "ok", "deleted": 1}
    assert called == [(_TX, "tpl-1", "2026-09-01")]


def test_deleting_one_occurrence_does_not_touch_the_rest(client, monkeypatch):
    _occurrence(monkeypatch, _SERIES)
    monkeypatch.setattr(app_module.db, "delete_one_occurrence", lambda *a: (True, None))
    monkeypatch.setattr(app_module.db, "delete_occurrences_from",
                        lambda *a: pytest.fail("נמחקה כל הסדרה"))

    assert client.delete(f"/api/transactions/{_TX}?mode=one").status_code == 200


# ─── "את זו וכל הבאות" ──────────────────────────────────────────────────────

def test_deleting_from_here_onward_reports_how_many_went(client, monkeypatch):
    _occurrence(monkeypatch, _SERIES)
    monkeypatch.setattr(app_module.db, "delete_occurrences_from",
                        lambda tpl, d, fam: (4, None))

    res = client.delete(f"/api/transactions/{_TX}?mode=later")

    assert res.get_json() == {"status": "ok", "deleted": 4}


# ─── עסקה רגילה לא השתנתה ───────────────────────────────────────────────────

def test_an_ordinary_transaction_is_untouched(client, monkeypatch):
    """בקרת-נגד, והחשובה כאן: רוב המחיקות הן של עסקה רגילה, והן חייבות
    להמשיך לעבוד בדיוק כמו קודם — כולל "בטל"."""
    _occurrence(monkeypatch, None)
    deleted = []
    monkeypatch.setattr(app_module.db, "delete_transaction",
                        lambda tx, fam: (deleted.append(tx) or True))

    res = client.delete(f"/api/transactions/{_TX}")

    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}
    assert deleted == [_TX]


def test_an_unknown_series_state_refuses_rather_than_guessing(client, monkeypatch):
    def _boom(*a):
        raise app_module.db.DataUnavailable("recurring_occurrence")
    monkeypatch.setattr(app_module.db, "recurring_occurrence", _boom)
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


# ─── מה שהמשתמש רואה ────────────────────────────────────────────────────────

def _js():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    return (root / "frontend/static/js/transactions.js").read_text(encoding="utf-8")


def _dialog():
    js = _js()
    block = js[js.index("function askAboutSeries("):]
    return block[:block.index("function sendSeriesDelete(")]


def test_the_dialog_asks_the_calendar_question():
    block = _dialog()

    assert "רק את זו" in block
    assert "את זו וכל הבאות" in block
    assert "העסקה הזאת חוזרת" in block


def test_the_safe_option_is_the_confirm_button():
    """מחיקת מופע אחד היא הפעולה הצפויה; מחיקת כל השאר עוברת אישור
    שני שמציג את המספר."""
    block = _dialog()

    assert "confirmText: 'רק את זו'" in block
    assert "למחוק את זו וכל הבאות?" in block


def test_backing_out_of_either_dialog_deletes_nothing():
    """נסיגה מחזירה ‎null‎. דיאלוג שני שמפרש ‎null‎ כאישור הוא בדיוק
    הבאג שכבר היה במחיקת פרויקט."""
    block = _dialog()

    assert "if (onlyThis === null) return;" in block
    assert "if (sure !== true) return;" in block


def test_no_undo_is_offered_for_either():
    """שחזור של מופע בודד היה מחזיר גם את הדילוג שנרשם עליו, ושל
    סדרה שלמה — עשרות שורות."""
    js = _js()
    block = js[js.index("function sendSeriesDelete("):]
    block = block[:block.index("function deleteWithUndo(")]

    assert "label: 'בטל'" not in block
    assert "שאר הסדרה נשארה" in block


# ─── שתי שאלות במקום אחת ────────────────────────────────────────────────────

def test_a_recurring_transaction_is_not_asked_the_generic_question_first():
    """מתן ראה "למחוק את העסקה? / הפעולה תסיר את העסקה מכל הדוחות
    והגרפים" — משפט שנכון לעסקה בודדת ומטעה לחלוטין כשמאחוריה סדרה.

    השאלה האמיתית מגיעה אחריה, מהשרת, אבל מי שרואה שאלה מנוסחת
    ומוחלטת מניח שזו השאלה היחידה — ולוחץ ביטול."""
    js = _js()
    block = js[js.index("function confirmDelete("):]
    block = block[:block.index("function deleteWithUndo(")]

    assert "txData.isRecurring || txData.recurringParentId" in block
    assert "Promise.resolve(true)" in block


def test_every_delete_path_goes_through_the_same_gate():
    """שלושה מסלולי מחיקה — המודאל, העורך בשורה, וההחלקה. שלושתם
    שאלו את השאלה הגנרית בנפרד, וכל אחד היה יכול להישאר מאחור."""
    js = _js()

    assert js.count("title: 'למחוק את העסקה?'") == 1, "נשארה שאלה גנרית מקומית"
    assert js.count("confirmDelete(") == 4, "לא כל מסלולי המחיקה עוברים בשער"


def test_an_ordinary_transaction_still_gets_asked():
    """בקרת-נגד: רוב המחיקות הן של עסקה רגילה, ושם השאלה נחוצה."""
    js = _js()
    block = js[js.index("function confirmDelete("):]
    block = block[:block.index("function deleteWithUndo(")]

    assert "הפעולה תסיר את העסקה מכל הדוחות והגרפים" in block
    assert "confirmText: 'מחק עסקה'" in block
