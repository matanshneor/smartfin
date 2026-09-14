"""
בדיקות לטיפול בפרמטרי year/month של עמוד החודש.

התגלה בפרודקשן תוך כדי אימות של Sentry: ‎/month?month=99999999 החזיר 500.
‏type=int מוודא שהערך מספר, לא שהוא חודש קיים, ומשם _month_label עשה
‎_HEBREW_MONTHS[99999999] וזרק IndexError. כל אחד עם הכתובת יכול היה
להפיל למשתמש את העמוד.

המקרה המסוכן יותר היה דווקא השקט: אינדקס שלילי תקין בפייתון, כך
ש-‎?month=-5 החזיר "אוגוסט" בלי להתלונן — עמוד שנראה תקין ומציג את החודש
הלא נכון.

הבדיקות לא נוגעות ב-Supabase: הן מעמידות session בלי family_id, מסלול
שמרנדר את העמוד הריק ולא פונה לבסיס הנתונים.
"""
import pytest

from backend.app import _month_label, app

pytestmark = pytest.mark.unit


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        with c.session_transaction() as sess:
            # משתמש מחובר בלי משפחה — עובר את login_required ונעצר לפני כל
            # שליפה, כך שהקוד שמעבד את הפרמטרים כן רץ
            sess["user_id"]        = "00000000-0000-0000-0000-000000000000"
            sess["user_name"]      = "בדיקה"
            sess["avatar_initial"] = "ב"
            sess["family_id"]      = None
        yield c


@pytest.mark.parametrize("query", [
    "month=99999999",            # הערך שהפיל את הפרודקשן
    "month=13",
    "month=0",
    "month=-5",                  # החזיר "אוגוסט" בשקט
    "year=99999999",
    "year=-1",
    "year=99999999&month=99999999",
    "month=abc",                 # לא מספר — Flask נופל לברירת המחדל
    "month=",
])
def test_out_of_range_params_render_instead_of_crashing(client, query):
    response = client.get(f"/month?{query}")

    assert response.status_code == 200, f"?{query} לא רונדר ({response.status_code})"


def test_a_valid_month_is_respected(client):
    """בקרת-נגד: ההקשחה לא אמורה לרמוס קלט תקין."""
    response = client.get("/month?year=2026&month=3")

    assert response.status_code == 200
    assert "מרץ 2026" in response.get_data(as_text=True)


@pytest.mark.parametrize("month", [13, 0, -5, 99999999])
def test_month_label_never_indexes_out_of_range(month):
    """‎_month_label נקרא מכמה מסלולים, אז הוא מוקשח בנפרד מהוולידציה
    שבכניסה — ולא מסתמך עליה."""
    label = _month_label(2026, month)

    assert label.endswith("2026")
    assert label.split()[0], "שם החודש לא אמור לצאת ריק"


@pytest.mark.parametrize("month,expected", [(1, "ינואר"), (12, "דצמבר")])
def test_month_label_keeps_valid_months(month, expected):
    assert _month_label(2026, month) == f"{expected} 2026"
