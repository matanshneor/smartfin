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


def _steps(repo_root):
    html = (repo_root / _TEMPLATE).read_text(encoding="utf-8")
    tags = _STEP.findall(html)
    assert tags, "לא נמצא אף שלב באשף — כנראה השתנה המבנה והבדיקה כבר לא בודקת כלום"
    return tags


@pytest.fixture
def repo_root():
    from pathlib import Path
    return Path(__file__).resolve().parent.parent


def _is_hidden_inline(tag: str) -> bool:
    return re.search(r'style="[^"]*display\s*:\s*none', tag, re.IGNORECASE) is not None


def test_exactly_one_step_is_visible_on_arrival(repo_root):
    """הלב: משתמש חדש רואה מסך אחד, לא שניים זה על גבי זה."""
    visible = [t for t in _steps(repo_root) if not _is_hidden_inline(t)]

    assert len(visible) == 1, (
        f"{len(visible)} שלבים גלויים בטעינה במקום אחד — "
        f"משתמש חדש יראה אותם זה על גבי זה. השלבים הגלויים: {visible}"
    )


def test_the_visible_step_is_the_first_one(repo_root):
    """בקרת-נגד: שלב אחד גלוי זה לא מספיק אם זה השלב הלא נכון."""
    visible = [t for t in _steps(repo_root) if not _is_hidden_inline(t)]

    assert 'id="step0"' in visible[0], (
        f"השלב הגלוי אינו מסך הפתיחה אלא: {visible[0]}"
    )


def test_hiding_a_step_does_not_depend_on_remembering(repo_root):
    """מה שמונע את חזרת הבאג: ההסתרה היא ברירת המחדל ב-CSS, ולא משהו
    שצריך לזכור לכתוב על כל שלב חדש בנפרד."""
    css = (repo_root / _STYLESHEET).read_text(encoding="utf-8")

    assert re.search(r"\.onboarding-step\s*\{[^}]*display\s*:\s*none", css), \
        "אין כלל CSS שמסתיר שלב כברירת מחדל — שלב חדש שיישכח יופיע שוב"
    assert re.search(r"\.onboarding-step#step0\s*\{[^}]*display\s*:\s*block", css), \
        "מסך הפתיחה לא מוחזר לגלוי, כך שהאשף ייפתח ריק"
