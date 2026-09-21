"""המסלולים שמזיזים כסף — הפעם באמת מורצים.

הפער שהבדיקות האלה סוגרות: ‎add_transaction‎, ‎update_transaction‎,
‎delete_transaction‎, ‎reset_transactions‎ ו-‎update_recurring_template‎
לא הוזכרו בשום בדיקה בסוויטה. מאות בדיקות רצו ירוקות מעל מסלול הכסף
המרכזי בלי לגעת בו: הכיסוי היחיד היה שורת ה-401 של "לא מחובר".

זה אומר ששבירה של ההוספה, של העריכה או של המחיקה הייתה עולה לאוויר
בלי שאף בדיקה תיפול. רשת הביטחון הייתה פרוסה מתחת להכול חוץ מהחלק
שמזיז כסף.

הבדיקות כאן מריצות את המסלול האמיתי ואת פונקציית הנתונים האמיתית מעל
כפיל בזיכרון (‎tests/_fake_db.py‎), ובודקות **מה נשמר בפועל** — לא מה
הוחזר. הסיבה: כמעט כל באג בקבוצה הזאת התבטא בדיוק בפער הזה, תשובה
שאומרת "נשמר" מעל מסד שלא נגעו בו.
"""
import pytest

from backend import app as app_module
from backend import supabase_config as db
from backend.app import app, limiter
from tests._fake_db import FakeSupabase

pytestmark = pytest.mark.unit

_FAM   = "11111111-1111-1111-1111-111111111111"
_OTHER = "99999999-9999-9999-9999-999999999999"
_ME    = "22222222-2222-2222-2222-222222222222"
_SPOUSE = "33333333-3333-3333-3333-333333333333"

_CAT_FOOD   = "aaaaaaaa-0000-0000-0000-000000000001"
_CAT_SALARY = "aaaaaaaa-0000-0000-0000-000000000002"

_CATEGORIES = [
    {"id": _CAT_FOOD,   "name": "מכולת",  "type": "expense", "family_id": _FAM},
    {"id": _CAT_SALARY, "name": "משכורת", "type": "income",  "family_id": _FAM},
]


class _Money:
    """הכפיל, בתוספת קיצורים שקוראים כמו המשפט שהבדיקה בודקת."""

    def __init__(self, fake, client):
        self.fake = fake
        self.client = client

    @property
    def transactions(self):
        return self.fake.rows("transactions")

    def only(self):
        rows = self.transactions
        assert len(rows) == 1, f"ציפיתי לשורה אחת, יש {len(rows)}: {rows}"
        return rows[0]

    def post(self, **body):
        return self.client.post("/api/transactions", json=body)

    def put(self, tx_id, **body):
        return self.client.put(f"/api/transactions/{tx_id}", json=body)

    def delete(self, tx_id, **params):
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return self.client.delete(f"/api/transactions/{tx_id}" + (f"?{query}" if query else ""))


@pytest.fixture
def money(monkeypatch):
    """מסלול אמיתי → פונקציית נתונים אמיתית → טבלה בזיכרון."""
    limiter.reset()
    app.config["TESTING"] = True

    fake = FakeSupabase(transactions=[])
    monkeypatch.setattr(db, "get_client", lambda: fake)

    # שכנים שאינם הנושא הנבדק. השיוך כבוי כברירת מחדל — כך העסקה
    # נשמרת כמשפחתית, וכל בדיקה שצריכה שיוך מדליקה אותו במפורש.
    monkeypatch.setattr(db, "get_family_settings",
                        lambda fid: {"owner_attribution": {"expense": False, "income": False,
                                                           "savings": False}})
    monkeypatch.setattr(db, "get_categories", lambda fid: list(_CATEGORIES))
    monkeypatch.setattr(db, "get_family_members",
                        lambda fid: [{"id": _ME, "name": "מתן"},
                                     {"id": _SPOUSE, "name": "אור"}])
    monkeypatch.setattr(db, "get_profile", lambda uid: {"id": uid, "workplace": "מקום"})
    monkeypatch.setattr(db, "materialize_recurring", lambda fid: (0, True))
    monkeypatch.setattr(db, "recurring_occurrence", lambda tx, fid: (None, True))
    monkeypatch.setattr(db, "is_recurring_instance", lambda tx, fid: False)
    monkeypatch.setattr(db, "get_transaction_receipt_path", lambda tx, fid: None)

    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = _ME
            sess["family_id"] = _FAM
            sess["user_name"] = "מתן"
            sess["user_email"] = "matan@example.com"
        yield _Money(fake, c)


def _seed(money, **overrides):
    """שורה קיימת בטבלה, כמו שהמסד היה מחזיר אותה."""
    row = {"id": "tx-1", "family_id": _FAM, "amount": 100.0, "type": "expense",
           "date": "2026-09-10", "description": "קפה", "category_id": _CAT_FOOD,
           "user_id": None, "is_recurring": False}
    row.update(overrides)
    money.fake.tables["transactions"].append(row)
    return row


# ═══ הוספה ═══════════════════════════════════════════════════════════════════

def test_adding_a_transaction_stores_the_amount_that_was_sent(money):
    """הלב, וזו הבדיקה שלא הייתה: 250.50 נכנסו — 250.50 נשמרו."""
    response = money.post(amount="250.50", type="expense", date="2026-09-15",
                          description="מכולת", category_id=_CAT_FOOD)

    assert response.status_code == 201, response.get_json()
    row = money.only()
    assert row["amount"] == 250.50
    assert row["type"] == "expense"
    assert row["date"] == "2026-09-15"
    assert row["description"] == "מכולת"
    assert row["category_id"] == _CAT_FOOD


def test_the_transaction_is_stamped_with_the_callers_family(money):
    """הבידוד עצמו. ‎family_id‎ נלקח מהסשן ולא מגוף הבקשה — אחרת אפשר
    לרשום עסקה לתוך משפחה אחרת."""
    money.post(amount="80", type="expense", date="2026-09-15",
               family_id=_OTHER, category_id=_CAT_FOOD)

    assert money.only()["family_id"] == _FAM


@pytest.mark.parametrize("amount,why", [
    ("-500",        "סכום שלילי"),
    ("0",           "אפס"),
    ("inf",         "אינסוף"),
    ("nan",         "לא-מספר"),
    ("999999999",   "מעל תקרת NUMERIC(10,2)"),
    ("0.001",       "מתחת לאגורה — מתעגל לאפס"),
    ("abc",         "לא מספר בכלל"),
])
def test_a_bad_amount_is_refused_and_nothing_is_written(money, amount, why):
    """‎422‎ לבד לא מספיק: השאלה היא אם משהו נשמר לפני הסירוב."""
    response = money.post(amount=amount, type="expense", date="2026-09-15")

    assert response.status_code == 422, f"{why} התקבל"
    assert money.transactions == [], f"{why} נשמר למרות הסירוב"


@pytest.mark.parametrize("tx_type", ["transfer", "", "EXPENSE", "הוצאה"])
def test_an_unknown_type_is_refused_and_nothing_is_written(money, tx_type):
    response = money.post(amount="50", type=tx_type, date="2026-09-15")

    assert response.status_code == 422
    assert money.transactions == []


def test_a_category_from_another_family_is_refused(money):
    """הקטגוריה מגיעה מהלקוח. בלי בדיקת שייכות אפשר לתלות עסקה על
    קטגוריה של משפחה אחרת, והפילוח החודשי נשבר בשקט."""
    response = money.post(amount="50", type="expense", date="2026-09-15",
                          category_id="לא-שלי")

    assert response.status_code == 422
    assert money.transactions == []


def test_a_category_of_the_wrong_type_is_refused(money):
    """קטגוריית משכורת על הוצאה — הסכום היה נספר בצד הלא נכון."""
    response = money.post(amount="50", type="expense", date="2026-09-15",
                          category_id=_CAT_SALARY)

    assert response.status_code == 422
    assert money.transactions == []


def test_an_impossible_date_is_refused_and_nothing_is_written(money):
    """תאריך הוא מה שהריץ את מנוע העסקאות הקבועות עד התקרה: עסקה
    קבועה מ-1000 ייצרה 500 שורות אמיתיות בקריאה אחת."""
    response = money.post(amount="50", type="expense", date="1000-01-01")

    assert response.status_code == 422
    assert money.transactions == []


def test_a_series_that_ends_before_it_starts_is_refused(money):
    response = money.post(amount="50", type="expense", date="2026-09-15",
                          is_recurring=True, recurring_frequency="monthly_1",
                          recurring_end_date="2026-08-01")

    assert response.status_code == 422
    assert money.transactions == []


def test_an_expense_is_attributed_to_the_caller_when_attribution_is_on(money, monkeypatch):
    monkeypatch.setattr(db, "get_family_settings",
                        lambda fid: {"owner_attribution": {"expense": True}})

    money.post(amount="50", type="expense", date="2026-09-15")

    assert money.only()["user_id"] == _ME


def test_an_expense_cannot_be_hung_on_someone_outside_the_family(money, monkeypatch):
    """זיוף שיוך: ה-uuid הגיע מהלקוח, ו-RLS בודקת רק ‎family_id‎."""
    monkeypatch.setattr(db, "get_family_settings",
                        lambda fid: {"owner_attribution": {"expense": True}})

    response = money.post(amount="50", type="expense", date="2026-09-15",
                          owner="44444444-4444-4444-4444-444444444444")

    assert response.status_code == 422
    assert money.transactions == []


def test_attribution_that_is_off_stores_the_transaction_as_shared(money):
    """מי שכיבה את השיוך לא אמור לקבל אותו בחזרה דרך גוף הבקשה."""
    money.post(amount="50", type="expense", date="2026-09-15", owner=_SPOUSE)

    assert money.only()["user_id"] is None


def test_a_new_recurring_transaction_fills_in_its_occurrences(money, monkeypatch):
    """עסקה קבועה שנוספת רטרואקטיבית חייבת להשלים את מה שחסר מיד,
    אחרת החודש נראה ריק עד הכניסה הבאה."""
    calls = []
    monkeypatch.setattr(db, "materialize_recurring",
                        lambda fid: (calls.append(fid), (0, True))[1])

    money.post(amount="7000", type="expense", date="2026-09-01",
               is_recurring=True, recurring_frequency="monthly_1")

    assert calls == [_FAM]
    assert money.only()["is_recurring"] is True


def test_a_plain_transaction_does_not_run_the_recurring_engine(money, monkeypatch):
    """בקרת-נגד: המנוע יוצר שורות אמיתיות, ואסור שירוץ סתם."""
    calls = []
    monkeypatch.setattr(db, "materialize_recurring",
                        lambda fid: (calls.append(fid), (0, True))[1])

    money.post(amount="50", type="expense", date="2026-09-15")

    assert calls == []


# ═══ עריכה ═══════════════════════════════════════════════════════════════════

def test_editing_a_transaction_changes_what_is_stored(money):
    _seed(money, amount=100.0, description="קפה")

    response = money.put("tx-1", amount="180", type="expense", date="2026-09-11",
                         description="קפה וכריך", category_id=_CAT_FOOD)

    assert response.status_code == 200, response.get_json()
    row = money.only()
    assert row["amount"] == 180.0
    assert row["description"] == "קפה וכריך"
    assert row["date"] == "2026-09-11"


def test_editing_a_transaction_that_is_gone_says_so(money):
    """הבאג המקורי: בן משפחה אחר מחק את השורה לפני שנייה, והעורך
    קיבל ‎200 {"status":"ok"}‎ והאמין שהעריכה נקלטה."""
    response = money.put("tx-נעלם", amount="180", type="expense", date="2026-09-11")

    assert response.status_code == 404
    assert response.get_json().get("status") != "ok"


def test_editing_cannot_reach_into_another_family(money):
    """אותו מסלול, שורה של משפחה אחרת: חייב להיראות כמו לא-קיים."""
    _seed(money, id="tx-זר", family_id=_OTHER, amount=100.0)

    response = money.put("tx-זר", amount="999", type="expense", date="2026-09-11")

    assert response.status_code == 404
    assert money.only()["amount"] == 100.0, "עסקה של משפחה אחרת נערכה"


def test_an_occurrence_cannot_become_a_second_template(money, monkeypatch):
    """סימון "עסקה קבועה" על מופע קיים ייצר סדרה מקבילה — שכר דירה
    פעמיים בחודש, לתמיד, בלי שום דרך לראות למה."""
    _seed(money, id="tx-מופע")
    monkeypatch.setattr(db, "is_recurring_instance", lambda tx, fid: True)

    response = money.put("tx-מופע", amount="7000", type="expense",
                         date="2026-09-01", is_recurring=True,
                         recurring_frequency="monthly_1")

    assert response.status_code == 422
    assert money.only()["is_recurring"] is False, "נוצרה סדרה שנייה"


def test_an_unknown_series_state_refuses_rather_than_guesses(money, monkeypatch):
    """סדרה כפולה היא נזק שאי אפשר לבטל; ניסיון חוזר כן."""
    _seed(money, id="tx-מופע")
    def _boom(tx, fid):
        raise db.DataUnavailable("is_recurring_instance")
    monkeypatch.setattr(db, "is_recurring_instance", _boom)

    response = money.put("tx-מופע", amount="7000", type="expense",
                         date="2026-09-01", is_recurring=True)

    assert response.status_code == 503
    assert money.only()["is_recurring"] is False


@pytest.mark.parametrize("amount", ["-500", "0", "inf", "999999999"])
def test_a_bad_amount_in_an_edit_leaves_the_old_value_alone(money, amount):
    _seed(money, amount=100.0)

    response = money.put("tx-1", amount=amount, type="expense", date="2026-09-11")

    assert response.status_code == 422
    assert money.only()["amount"] == 100.0


# ═══ מחיקה ═══════════════════════════════════════════════════════════════════

def test_deleting_a_transaction_removes_it(money):
    _seed(money)

    response = money.delete("tx-1")

    assert response.status_code == 200
    assert money.transactions == []


def test_deleting_something_that_is_not_there_does_not_say_ok(money):
    """‎delete_transaction‎ החזירה ‎True‎ גם כששום שורה לא נגעה."""
    response = money.delete("tx-נעלם")

    assert response.get_json()["status"] != "ok"
    assert response.status_code == 500


def test_deleting_cannot_reach_into_another_family(money):
    _seed(money, id="tx-זר", family_id=_OTHER)

    response = money.delete("tx-זר")

    assert response.get_json()["status"] != "ok"
    assert len(money.transactions) == 1, "עסקה של משפחה אחרת נמחקה"


def test_deleting_a_recurring_transaction_asks_before_it_touches_anything(money, monkeypatch):
    """בלי ‎mode‎ נשאלת השאלה — ולא נמחק כלום בינתיים."""
    _seed(money, id="tx-קבועה", is_recurring=True)
    monkeypatch.setattr(db, "recurring_occurrence",
                        lambda tx, fid: ({"template_id": "tx-קבועה",
                                          "date": "2026-09-01", "later": 4}, True))

    response = money.delete("tx-קבועה")

    assert response.status_code == 409
    assert response.get_json() == {"needs_choice": True, "later": 4}
    assert len(money.transactions) == 1, "נמחק לפני שנשאלה השאלה"


def test_an_unknown_series_state_refuses_to_delete_blindly(money, monkeypatch):
    _seed(money, id="tx-קבועה")
    def _boom(tx, fid):
        raise db.DataUnavailable("recurring_occurrence")
    monkeypatch.setattr(db, "recurring_occurrence", _boom)

    response = money.delete("tx-קבועה")

    assert response.status_code == 503
    assert len(money.transactions) == 1


# ═══ איפוס — הפעולה ההרסנית ביותר ════════════════════════════════════════════

@pytest.fixture
def reset(money, monkeypatch):
    class _Session:
        access_token = "token"
    monkeypatch.setattr(db, "sign_in", lambda e, p: (type("R", (), {"session": _Session})(), None))
    monkeypatch.setattr(db, "set_auth_token", lambda t: None)
    monkeypatch.setattr(db, "is_family_manager", lambda: True)
    return money


def test_resetting_the_family_deletes_only_this_family(reset):
    _seed(reset, id="a"); _seed(reset, id="b")
    _seed(reset, id="זר", family_id=_OTHER)

    response = reset.client.post("/api/account/reset",
                                 json={"password": "pw", "scope": "family"})

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["deleted"] == 2
    assert [r["id"] for r in reset.transactions] == ["זר"]


def test_resetting_mine_leaves_everyone_elses_money_alone(reset):
    """הטעות כאן היא חד-כיוונית: מי שביקש לאפס את שלו ומחק גם את של
    בן הזוג לא יכול להחזיר את זה."""
    _seed(reset, id="שלי", user_id=_ME)
    _seed(reset, id="שלה", user_id=_SPOUSE)

    response = reset.client.post("/api/account/reset",
                                 json={"password": "pw", "scope": "mine"})

    assert response.get_json()["deleted"] == 1
    assert [r["id"] for r in reset.transactions] == ["שלה"]


def test_a_wrong_password_deletes_nothing(reset, monkeypatch):
    _seed(reset, id="a")
    monkeypatch.setattr(db, "sign_in", lambda e, p: (None, "invalid"))

    response = reset.client.post("/api/account/reset",
                                 json={"password": "לא נכון", "scope": "family"})

    assert response.status_code == 403
    assert len(reset.transactions) == 1


def test_only_the_manager_can_wipe_the_whole_family(reset, monkeypatch):
    """הפעולה ההרסנית ביותר הייתה פתוחה לכל חבר עם הסיסמה של עצמו."""
    _seed(reset, id="a")
    monkeypatch.setattr(db, "is_family_manager", lambda: False)

    response = reset.client.post("/api/account/reset",
                                 json={"password": "pw", "scope": "family"})

    assert response.status_code == 403
    assert len(reset.transactions) == 1, "לא-מנהל מחק את עסקאות המשפחה"


def test_a_member_who_is_not_the_manager_can_still_reset_their_own(reset, monkeypatch):
    """בקרת-נגד: זה הכסף של מי שמבקש."""
    _seed(reset, id="שלי", user_id=_ME)
    monkeypatch.setattr(db, "is_family_manager", lambda: False)

    response = reset.client.post("/api/account/reset",
                                 json={"password": "pw", "scope": "mine"})

    assert response.status_code == 200
    assert reset.transactions == []


def test_resetting_an_empty_family_is_not_a_failure(reset):
    """אפס שורות היא תוצאה תקינה, לא שגיאה."""
    response = reset.client.post("/api/account/reset",
                                 json={"password": "pw", "scope": "family"})

    assert response.status_code == 200
    assert response.get_json()["deleted"] == 0


# ═══ עסקה קבועה — סנכרון התבנית ══════════════════════════════════════════════

def test_syncing_a_template_changes_only_the_template(money):
    """מופעים שכבר נוצרו הם היסטוריה ואסור לכתוב אותם מחדש."""
    _seed(money, id="תבנית", amount=7000.0, is_recurring=True)
    _seed(money, id="מופע", amount=7000.0, is_recurring=False)

    response = money.client.put("/api/recurring/תבנית/sync", json={"amount": "7500"})

    assert response.status_code == 200, response.get_json()
    rows = {r["id"]: r["amount"] for r in money.transactions}
    assert rows["תבנית"] == 7500.0
    assert rows["מופע"] == 7000.0, "היסטוריה נכתבה מחדש"


@pytest.mark.parametrize("amount", ["-5000", "inf", "0", "999999999"])
def test_the_sync_route_validates_the_amount_like_every_other_write(money, amount):
    """זה היה המסלול הכותב היחיד עם ‎float()‎ חשוף — ‎-5000‎ ו-‎inf‎
    עברו את פייתון ונעצרו רק ב-CHECK של המסד, שחזר כ-500 סתום."""
    _seed(money, id="תבנית", amount=7000.0, is_recurring=True)

    response = money.client.put("/api/recurring/תבנית/sync", json={"amount": amount})

    assert response.status_code == 422, f"{amount} התקבל"
    assert money.only()["amount"] == 7000.0


def test_the_sync_route_validates_the_category_too(money, monkeypatch):
    """‎category_id‎ נכתב בלי שום בדיקת שייכות."""
    _seed(money, id="תבנית", amount=7000.0, is_recurring=True, type="expense")
    monkeypatch.setattr(db, "transaction_type", lambda tx, fid: "expense")

    response = money.client.put("/api/recurring/תבנית/sync",
                                json={"category_id": "של משפחה אחרת"})

    assert response.status_code == 422
    assert money.only()["category_id"] == _CAT_FOOD


def test_syncing_a_template_that_is_not_recurring_is_refused(money):
    """המסלול נועד לתבניות. שורה רגילה שתיפול לכאן הייתה נערכת בלי
    אף אחת מהבדיקות של מסלול העריכה הרגיל."""
    _seed(money, id="רגילה", amount=100.0, is_recurring=False)

    response = money.client.put("/api/recurring/רגילה/sync", json={"amount": "7500"})

    assert response.status_code == 404
    assert money.only()["amount"] == 100.0


def test_syncing_cannot_reach_into_another_family(money):
    _seed(money, id="זרה", family_id=_OTHER, amount=7000.0, is_recurring=True)

    response = money.client.put("/api/recurring/זרה/sync", json={"amount": "1"})

    assert response.status_code == 404
    assert money.only()["amount"] == 7000.0


# ═══ מונה הסריקות — המסלול היחיד שעולה כסף אמיתי ═════════════════════════════
#
# ‎record_receipt_scan‎ הופיע פעם אחת בכל הסוויטה, כ-stub בלי שום assert.
# מחיקת השורה שקוראת לו ביטלה את שתי התקרות — זו של המשפחה וזו הגלובלית
# — והשאירה את הסוויטה ירוקה. זה הקובץ שנכתב כדי לשמור על ההוצאה.

_SCAN = {"amount": 42.0, "merchant": "מכולת", "date": "2026-09-15",
         "category_name": "מכולת"}


@pytest.fixture
def scan(money, monkeypatch):
    monkeypatch.setattr(db, "receipt_scans_this_month", lambda fid: 0)
    monkeypatch.setattr(db, "receipt_scans_globally_this_month", lambda: 0)
    monkeypatch.setattr(db, "scan_receipt", lambda b, t, cats: (dict(_SCAN), None))
    monkeypatch.setattr(db, "upload_receipt", lambda tok, fid, b, t: ("path.jpg", None))
    return money


def _image(scan):
    import io
    return scan.client.post(
        "/api/receipts/scan",
        data={"image": (io.BytesIO(b"\xff\xd8\xff-fake-jpeg"), "receipt.jpg", "image/jpeg")},
        content_type="multipart/form-data",
    )


def test_a_successful_scan_is_counted(scan):
    """הלב: בלי הרישום הזה המכסה לא קיימת, וההוצאה על ה-API פתוחה."""
    response = _image(scan)

    assert response.status_code == 200, response.get_json()
    counted = scan.fake.rows("receipt_scans")
    assert len(counted) == 1, "הסריקה לא נספרה — המכסה אינה קיימת בפועל"
    assert counted[0]["family_id"] == _FAM
    assert counted[0]["user_id"] == _ME


def test_a_failed_scan_is_not_counted(scan, monkeypatch):
    """בקרת-נגד: אסור לחייב את המשפחה במכסה על סריקה שלא החזירה כלום."""
    monkeypatch.setattr(db, "scan_receipt", lambda b, t, cats: (None, "לא הצלחנו לקרוא"))

    _image(scan)

    assert scan.fake.rows("receipt_scans") == []


def test_a_scan_that_could_not_be_stored_is_still_counted(scan, monkeypatch):
    """הקריאה ל-OpenAI כבר נעשתה ושולמה. כישלון העלאה לא מחזיר את הכסף."""
    monkeypatch.setattr(db, "upload_receipt", lambda tok, fid, b, t: (None, "storage"))

    assert _image(scan).status_code == 200
    assert len(scan.fake.rows("receipt_scans")) == 1


def test_the_family_ceiling_blocks_the_scan_before_it_costs_anything(scan, monkeypatch):
    called = []
    monkeypatch.setattr(db, "receipt_scans_this_month", lambda fid: db.RECEIPT_MONTHLY_LIMIT)
    monkeypatch.setattr(db, "scan_receipt",
                        lambda b, t, cats: (called.append(1), (dict(_SCAN), None))[1])

    response = _image(scan)

    assert response.status_code == 429
    assert called == [], "הסריקה רצה ושולמה למרות שהמכסה נוצלה"
    assert scan.fake.rows("receipt_scans") == []


def test_the_global_ceiling_blocks_everyone(scan, monkeypatch):
    """התקרה הגלובלית היא ההגנה על חשבון ה-OpenAI עצמו."""
    called = []
    monkeypatch.setattr(db, "receipt_scans_globally_this_month",
                        lambda: db.RECEIPT_GLOBAL_MONTHLY_LIMIT)
    monkeypatch.setattr(db, "scan_receipt",
                        lambda b, t, cats: (called.append(1), (dict(_SCAN), None))[1])

    response = _image(scan)

    assert response.status_code == 503
    assert called == []


def test_a_ceiling_that_cannot_be_read_refuses_rather_than_allows(scan, monkeypatch):
    """אישור כשהבדיקה נכשלה מבטל בפועל את ההגבלה — זו הוצאה אמיתית."""
    called = []
    def _boom(fid):
        raise db.DataUnavailable("receipt_scans_this_month")
    monkeypatch.setattr(db, "receipt_scans_this_month", _boom)
    monkeypatch.setattr(db, "scan_receipt",
                        lambda b, t, cats: (called.append(1), (dict(_SCAN), None))[1])

    response = _image(scan)

    assert response.status_code == 503
    assert called == []


def test_a_file_that_is_not_an_image_never_reaches_the_scanner(scan, monkeypatch):
    import io
    called = []
    monkeypatch.setattr(db, "scan_receipt",
                        lambda b, t, cats: (called.append(1), (dict(_SCAN), None))[1])

    response = scan.client.post(
        "/api/receipts/scan",
        data={"image": (io.BytesIO(b"%PDF-1.4"), "x.pdf", "application/pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 422
    assert called == []
    assert scan.fake.rows("receipt_scans") == []


# ═══ מחיקת חשבון ═════════════════════════════════════════════════════════════

def test_deleting_the_account_requires_the_right_password(money, monkeypatch):
    """הפעולה שאי אפשר לבטל. סיסמה שגויה חייבת לעצור לפני ה-RPC."""
    monkeypatch.setattr(db, "sign_in", lambda e, p: (None, "invalid"))

    response = money.client.delete("/api/account", json={"password": "לא נכון"})

    assert response.status_code == 403
    assert money.fake.rpcs == [], "החשבון נמחק עם סיסמה שגויה"


def test_deleting_the_account_without_a_password_stops_first(money):
    response = money.client.delete("/api/account", json={})

    assert response.status_code == 422
    assert money.fake.rpcs == []


def test_deleting_the_account_calls_the_archiving_function_and_ends_the_session(money, monkeypatch):
    class _Session:
        access_token = "token"
    monkeypatch.setattr(db, "sign_in",
                        lambda e, p: (type("R", (), {"session": _Session})(), None))
    monkeypatch.setattr(db, "set_auth_token", lambda t: None)

    response = money.client.delete("/api/account", json={"password": "pw"})

    assert response.status_code == 200
    assert [name for name, _ in money.fake.rpcs] == ["delete_my_account"]
    with money.client.session_transaction() as sess:
        assert "user_id" not in sess, "הסשן שרד את מחיקת החשבון"
