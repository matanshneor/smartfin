"""
בדיקות לאשף ההרשמה — המסך הראשון שמשתמש חדש רואה.

האשף בנוי משישה ‎<section class="onboarding-step">‎ באותו עמוד, וה-JS מחליף
ביניהם. ההסתרה הייתה ‎style="display:none"‎ שנכתב ידנית על כל שלב בנפרד,
ובאחד מהם זה נשכח — כך שמשתמש חדש קיבל את מסך הבחירה ואת השאלה על שם
המשפחה זה על גבי זה, ברגע הכי רגיש במוצר.

הבדיקות כאן לא בודקות "האם ל-step1 יש display:none" אלא את התכונה עצמה:
שלב אחד בדיוק גלוי. זה מה שיתפוס גם את השלב השביעי שמישהו יוסיף בעתיד
וישכח להסתיר, וזו הסיבה שהבאג הזה היה אפשרי מלכתחילה.
"""
import re

import pytest

pytestmark = pytest.mark.unit

_TEMPLATE = "frontend/templates/onboarding.html"
_STYLESHEET = "frontend/static/css/style.css"

_STEP = re.compile(
    r'<section[^>]*class="[^"]*\bonboarding-step\b[^"]*"[^>]*>', re.IGNORECASE
)


_CSS_BLOCK = re.compile(r"\.onboarding-step#(\w+)")

_FAM = "11111111-1111-1111-1111-111111111111"


def _render(repo_root, waiting_for):
    """מרנדרת את העמוד כפי שהוא מוגש בפועל.

    התבנית מחזיקה שני מסכי-פתיחה בלעדיים ‎({% if waiting_for %})‎, אז
    קריאת הקובץ כטקסט סופרת את שניהם ומדווחת על התנגשות שלא קיימת.
    מה שצריך להיבדק הוא מה שמגיע לדפדפן, בשתי ההגעות."""
    from backend import app as app_module
    from backend.app import app

    app.config["TESTING"] = True
    real = {}
    for name, fake in (
        ("family_needs_onboarding", lambda fid: True),
        ("get_family", lambda fid: {"id": _FAM, "name": "שניאור", "invite_code": "K4F2QX"}),
        ("get_family_members", lambda fid: [{"id": "me", "name": "מתן"}] +
            ([{"id": "other", "name": waiting_for}] if waiting_for else [])),
    ):
        real[name] = getattr(app_module.db, name)
        setattr(app_module.db, name, fake)
    try:
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess["user_id"] = "me"; sess["family_id"] = _FAM; sess["user_name"] = "מתן"
            return c.get("/onboarding").get_data(as_text=True)
    finally:
        for name, fn in real.items():
            setattr(app_module.db, name, fn)


def _steps(repo_root, waiting_for=None):
    tags = _STEP.findall(_render(repo_root, waiting_for))
    assert tags, "לא נמצא אף שלב באשף — כנראה השתנה המבנה והבדיקה כבר לא בודקת כלום"
    return tags


def _shown_by_css(repo_root, tag):
    """שלב בלי ‎display:none‎ בשורה עדיין מוסתר אם אין לו כלל CSS — ככה
    מסך ההמתנה נולד ריק לגמרי."""
    css = (repo_root / _STYLESHEET).read_text(encoding="utf-8")
    shown = set(_CSS_BLOCK.findall(css))
    ident = re.search(r'id="(\w+)"', tag)
    return bool(ident) and ident.group(1) in shown


@pytest.fixture
def repo_root():
    from pathlib import Path
    return Path(__file__).resolve().parent.parent


def _is_hidden_inline(tag: str) -> bool:
    return re.search(r'style="[^"]*display\s*:\s*none', tag, re.IGNORECASE) is not None


@pytest.mark.parametrize("waiting_for", [None, "אור"])
def test_exactly_one_step_is_visible_on_arrival(repo_root, waiting_for):
    """הלב: משתמש חדש רואה מסך אחד, לא שניים זה על גבי זה."""
    visible = [t for t in _steps(repo_root, waiting_for) if not _is_hidden_inline(t)]

    assert len(visible) == 1, (
        f"{len(visible)} שלבים גלויים בטעינה במקום אחד — "
        f"משתמש חדש יראה אותם זה על גבי זה. השלבים הגלויים: {visible}"
    )


@pytest.mark.parametrize("waiting_for,expected", [(None, "step0"), ("אור", "stepWaiting")])
def test_the_visible_step_is_the_first_one(repo_root, waiting_for, expected):
    """בקרת-נגד: שלב אחד גלוי זה לא מספיק אם זה השלב הלא נכון."""
    visible = [t for t in _steps(repo_root, waiting_for) if not _is_hidden_inline(t)]

    assert f'id="{expected}"' in visible[0], (
        f"השלב הגלוי אינו מסך הפתיחה אלא: {visible[0]}"
    )


@pytest.mark.parametrize("waiting_for", [None, "אור"])
def test_the_visible_step_is_actually_shown_by_the_stylesheet(repo_root, waiting_for):
    """היעדר ‎display:none‎ בשורה אינו נראוּת: ברירת המחדל ב-CSS מסתירה
    כל שלב, ומי שאין לו כלל משלו מרונדר לעמוד ריק."""
    visible = [t for t in _steps(repo_root, waiting_for) if not _is_hidden_inline(t)]

    assert _shown_by_css(repo_root, visible[0]), (
        f"אין כלל CSS שמציג את {visible[0]} — העמוד ייטען ריק"
    )


def test_hiding_a_step_does_not_depend_on_remembering(repo_root):
    """מה שמונע את חזרת הבאג: ההסתרה היא ברירת המחדל ב-CSS, ולא משהו
    שצריך לזכור לכתוב על כל שלב חדש בנפרד."""
    css = (repo_root / _STYLESHEET).read_text(encoding="utf-8")

    assert re.search(r"\.onboarding-step\s*\{[^}]*display\s*:\s*none", css), \
        "אין כלל CSS שמסתיר שלב כברירת מחדל — שלב חדש שיישכח יופיע שוב"
    assert "step0" in _CSS_BLOCK.findall(css), \
        "מסך הפתיחה לא מוחזר לגלוי, כך שהאשף ייפתח ריק"
