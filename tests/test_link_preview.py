"""
הקישור שנשלח בוואטסאפ, וההזמנה שמועתקת איתו.

זה מה שקורה בפועל כשמתן יפיץ את האפליקציה. קישור בלי תגיות שיתוף
מוצג כשורת טקסט חשופה — בלי שם, בלי תיאור ובלי תמונה — וזה נראה חשוד
בדיוק ברגע שמבקשים מאנשים למסור נתוני כסף.

ושיתוף ההזמנה העתיק שישה תווים ותו לא. מי שקיבל "K4F2QX" קיבל שישה
תווים בלי קישור ובלי הסבר, בזמן שדף הנחיתה מוכר את זה כ"מזמינים את
בני הבית עם קוד בן שישה תווים".
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT   = Path(__file__).resolve().parent.parent
_TPL    = _ROOT / "frontend/templates"
_JS     = _ROOT / "frontend/static/js"
_PUBLIC = ["landing.html", "login.html", "privacy.html", "terms.html"]


def _read(name):
    return (_TPL / name).read_text(encoding="utf-8")


# ─── תצוגה מקדימה בשיתוף ────────────────────────────────────────────────────

@pytest.mark.parametrize("page", _PUBLIC)
def test_every_public_page_previews_properly(page):
    html = _read(page)

    for tag in ("og:title", "og:description", "og:image", "og:url", "og:type"):
        assert f'property="{tag}"' in html, f"{page} חסר {tag}"
    assert 'name="twitter:card"' in html


@pytest.mark.parametrize("page", _PUBLIC)
def test_the_preview_image_is_absolute(page):
    """כתובת יחסית לא נפתרת אצל מי שמציג את התצוגה המקדימה — הוא
    שולף את העמוד משרת אחר לגמרי."""
    html = _read(page)
    block = html[html.index('property="og:image"'):]
    block = block[:block.index(">") + 1]

    assert "_external=True" in block


@pytest.mark.parametrize("page", _PUBLIC)
def test_each_page_says_what_it_is(page):
    """כותרת אחת לכל האתר הופכת כל קישור לזהה, וזה בדיוק מה שהתגיות
    נועדו למנוע."""
    html = _read(page)
    block = html[html.index("{% set og_title"):]
    title = block[:block.index("%}")]

    assert "SmartFin" in title
    assert len(title) > 30, "כותרת גנרית מדי"


def test_the_image_exists_and_is_the_right_shape():
    """1200×630 הוא מה ש-WhatsApp ופייסבוק מצפים לו; יחס אחר נחתך."""
    png = _ROOT / "frontend/static/icons/og-image.png"

    assert png.exists(), "אין תמונת תצוגה"
    data = png.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "לא PNG"
    width  = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    assert (width, height) == (1200, 630), f"המידות הן {width}×{height}"


# ─── ההזמנה שמועתקת ─────────────────────────────────────────────────────────

_HARNESS = r"""
const fs = require('fs'), g = globalThis;
g.window = { location: { origin: 'https://smartfin.up.railway.app' } };
g.document = { querySelectorAll: () => [] };
(0, eval)(fs.readFileSync(process.argv[2], 'utf8'));
console.log(JSON.stringify({
    named:   g.window.sfInviteMessage('K4F2QX', 'משפחת שניאור'),
    unnamed: g.window.sfInviteMessage('K4F2QX', ''),
}));
"""


def _messages():
    node = shutil.which("node")
    if not node:
        pytest.skip("node לא מותקן")
    h = _ROOT / "tests" / "_invite_harness.js"
    h.write_text(_HARNESS, encoding="utf-8")
    try:
        out = subprocess.run([node, str(h), str(_JS / "clipboard.js")],
                             capture_output=True, text=True, timeout=30)
    finally:
        h.unlink(missing_ok=True)
    assert out.returncode == 0, out.stderr[:600]
    return json.loads(out.stdout)


def test_the_invite_carries_a_link_not_just_six_characters():
    """הלב. בלי הקישור, המקבל לא יודע לאן ללכת עם הקוד."""
    msg = _messages()["named"]

    assert "K4F2QX" in msg
    assert "https://smartfin.up.railway.app/signup" in msg


def test_the_invite_says_who_is_inviting():
    msg = _messages()["named"]

    assert "משפחת שניאור" in msg
    assert "SmartFin" in msg


def test_a_family_without_a_name_still_reads_properly():
    """בקרת-נגד: שם המשפחה אופציונלי, והודעה עם חור באמצע גרועה
    מהודעה גנרית."""
    msg = _messages()["unnamed"]

    assert '""' not in msg
    assert "המשפחה שלנו" in msg
    assert "K4F2QX" in msg


def test_the_code_sits_on_its_own_line():
    """כדי שאפשר יהיה לסמן אותו בלחיצה ארוכה בלי לגרור נקודה."""
    msg = _messages()["named"]

    assert "\nK4F2QX\n" in msg
