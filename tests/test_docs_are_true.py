"""התיעוד מתאר את האפליקציה הזאת, לא אחת קודמת.

ה-README טען 46 מסלולים כשהיו 56, ו-29 מיגרציות כשהיו 41. ‎SPEC.md‎ תיאר
אפליקציה בלי פרויקטים, בלי סריקת קבלות, בלי תקציבים ובלי תפקיד מנהל —
כלומר בערך חצי ממה שקיים. הריפו ציבורי, וזה המסמך הראשון שמישהו קורא.

התיעוד נרקב כי שום דבר לא בדק אותו. הבדיקות כאן לא מוודאות שהוא כתוב
יפה — הן מוודאות שהמספרים שבו נכונים, ושהוא לא מחזיק פרטי חשבון אמיתיים.
כשמוסיפים מסלול או מיגרציה, אחת מהן תיפול ותגיד מה לעדכן.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_README = (_ROOT / "README.md").read_text(encoding="utf-8")
_SPEC = (_ROOT / "docs/SPEC.md").read_text(encoding="utf-8")


def _claimed(pattern, text=_README):
    """המספר שהתיעוד טוען. נכשל בקול אם הניסוח השתנה — בדיקה שלא מוצאת
    את מה שהיא בודקת עוברת תמיד, וזה גרוע מאשר לא לבדוק."""
    match = re.search(pattern, text)
    assert match, f"לא נמצאה הטענה בתיעוד: {pattern}"
    return int(match.group(1))


# ─── המספרים ────────────────────────────────────────────────────────────────

def test_the_readme_counts_the_routes_correctly():
    actual = len(re.findall(r"^@app\.route", (_ROOT / "backend/app.py")
                            .read_text(encoding="utf-8"), re.M))
    claimed = _claimed(r"all (\d+) routes")

    assert claimed == actual, (
        f"ה-README אומר {claimed} מסלולים, ובפועל יש {actual}. "
        f"עדכנו את README.md."
    )


def test_the_readme_counts_the_migrations_correctly():
    actual = len(list((_ROOT / "backend/supabase/migrations").glob("*.sql")))
    claimed = _claimed(r"database schema \((\d+) migrations\)")

    assert claimed == actual, (
        f"ה-README אומר {claimed} מיגרציות, ובפועל יש {actual}. "
        f"עדכנו את README.md."
    )


def test_the_readme_counts_the_tests_roughly_right():
    """כאן די בקירוב — הבדיקות גדלות כל הזמן, ומספר מדויק היה הופך את
    הבדיקה הזאת למטלה. מה שנתפס הוא סדר גודל שהתיישן."""
    collected = len(list((_ROOT / "tests").glob("test_*.py")))
    claimed = _claimed(r"(\d+) tests: \d+ unit")

    assert claimed >= collected * 5, (
        f"ה-README אומר {claimed} בדיקות ב-{collected} קבצים — נראה מיושן."
    )


# ─── מה שהתיעוד חייב להזכיר ─────────────────────────────────────────────────

@pytest.mark.parametrize("feature,needle", [
    ("פרויקטים",        "Projects"),
    ("סריקת קבלות",     "Receipt scanning"),
    ("תקציבי קטגוריות", "budget"),
    ("תפקיד מנהל",      "manager"),
    ("ייצוא CSV",       "CSV"),
    ("בדיקות בריאות",   "/health"),
])
def test_the_readme_mentions_every_major_feature(feature, needle):
    """תכונה שקיימת ולא מתועדת היא תכונה שאף אחד לא ימצא."""
    assert needle.lower() in _README.lower(), f"{feature} לא מוזכר ב-README"


# כותרת פרק ולא מילה בודדת: "פרויקט" מופיע גם באזכורים חולפים, כך שמחיקת
# הפרק כולו הייתה עוברת בשקט.
@pytest.mark.parametrize("feature,heading", [
    ("פרויקטים",        "פרויקטים"),
    ("סריקת קבלות",     "סריקת קבלות"),
    ("הרשאות",          "הרשאות"),
])
def test_the_spec_has_a_section_for_every_major_feature(feature, heading):
    headings = re.findall(r"^#{2,3} .*$", _SPEC, re.M)
    assert any(heading in h for h in headings), (
        f"אין ב-SPEC.md פרק על {feature}. הפרקים שיש: {headings}"
    )


def test_the_spec_describes_budgets():
    assert "תקציב חודשי" in _SPEC, "התקציבים לא מתוארים ב-SPEC.md"


def test_the_spec_is_not_stuck_on_four_pages():
    """הניסוח "4 עמודים" שרד שלוש תכונות שהוסיפו עמודים משלהן."""
    assert "## 4 עמודים" not in _SPEC


# ─── מה שאסור שיהיה בתיעוד ──────────────────────────────────────────────────

def test_no_real_account_details_are_published():
    """‎SPEC.md‎ החזיק שני חשבונות אמיתיים בשמם, עם הערה שהם חולקים
    סיסמה. הריפו ציבורי. אין שם הסיסמה עצמה — ויש שם חצי מהעבודה."""
    docs = {"README.md": _README, "docs/SPEC.md": _SPEC}
    for name, text in docs.items():
        found = re.findall(r"[A-Za-z0-9._%+-]+@(?!example\.|smartfin\.test)"
                           r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
        # כתובת יצירת הקשר של המוצר היא פרסום מכוון, לא דליפה.
        leaked = [e for e in found if e != "matanshneor1@gmail.com"]
        assert not leaked, f"{name} מפרסם כתובות אמיתיות: {leaked}"

    assert "סיסמה משותפת" not in _SPEC


# תבנית טלפון נייד ישראלי. הבדיקה הקודמת ניקתה **מיילים** בלבד, ושני
# מספרים אמיתיים של משתמשים אמיתיים ישבו בריפו הציבורי עם ההערה
# "מספר אמיתי מהמסד" — בזמן שיש במסד פונקציה, פתוחה ל-anon, שממירה
# טלפון לכתובת מייל. השומר שנבנה כדי לתפוס בדיוק את זה פספס אותו.
_ISRAELI_MOBILE = re.compile(r"\b0?5[0-9][- ]?\d{3}[- ]?\d{4}\b")

# המספרים שמותר להם להופיע: כולם 1234567 / 9876543 ובבירור לא של אף אחד.
_OBVIOUSLY_FAKE = re.compile(r"(1234567|9876543|0000000|1111111)")


@pytest.mark.parametrize("where", ["tests", "backend", "docs", "frontend"])
def test_no_real_phone_number_is_published(where):
    """מספר אמיתי של משתמש ברפו ציבורי הוא חצי מהעבודה של מי שמנסה
    להיכנס לחשבון שלו."""
    leaked = []
    for path in sorted((_ROOT / where).rglob("*")):
        if not path.is_file() or path.suffix not in (".py", ".html", ".js", ".md", ".sql"):
            continue
        for m in _ISRAELI_MOBILE.finditer(path.read_text(encoding="utf-8", errors="ignore")):
            # ההשוואה על הספרות בלבד: ‎54-123-4567‎ ו-‎0541234567‎ הם
            # אותו מספר, והמפרידים משתנים לפי ההקשר.
            if not _OBVIOUSLY_FAKE.search(re.sub(r"[- ]", "", m.group(0))):
                leaked.append(f"{path.relative_to(_ROOT)}: {m.group(0)}")

    assert not leaked, "מספרי טלפון שאינם בבירור בדויים:\n  " + "\n  ".join(leaked)


def test_the_docs_do_not_claim_rate_limiting_is_memory_only():
    """הטענה "in-memory, auth routes only" הייתה שגויה בשני חלקיה,
    ובכיוון המסוכן: היא מתארת הגנה חלשה מהקיימת, כך שמי שקורא אותה
    עלול "לתקן" בדיוק את מה שכבר עובד."""
    assert "in-memory, auth routes only" not in _README


def test_the_readme_does_not_send_people_to_deploy_around_ci():
    """‎railway up‎ עוקף את שער ה-CI. הוא עדיין קיים, אבל התיעוד חייב
    לומר שהוא עוקף — אחרת הוא מוצג כדרך המקבילה והשקולה."""
    if "railway up" in _README:
        window = _README[_README.index("railway up"):][:400]
        assert "skips" in window or "עוקף" in window, \
            "railway up מתועד בלי לומר שהוא מדלג על בדיקות ה-CI"


# ─── האזהרות התפעוליות ──────────────────────────────────────────────────────

# שלוש אזהרות שכבר גרמו לתקלה אמיתית, ואף אחת מהן אינה ניכרת מקריאת הקוד.
# הבדיקה מחפשת את **גוף** האזהרה ולא את שם הקובץ: "clock.py" מופיע גם בעץ
# הספריות, כך שמחיקת האזהרה עצמה לא הפילה כלום.
_LANDMINES = [
    ("worker אסינכרוני", ["--threads", "gevent", "singleton"]),
    ("שעון ישראל",       ["Asia/Jerusalem", "UTC", "clock.today()"]),
    ("אפס מדומה",        ["DataUnavailable", "false zero"]),
]


@pytest.mark.parametrize("name,phrases", _LANDMINES, ids=[m[0] for m in _LANDMINES])
def test_the_readme_carries_the_three_landmines(name, phrases):
    missing = [p for p in phrases if p not in _README]
    assert not missing, f"האזהרה על {name} נשחקה — חסר ב-README: {missing}"
