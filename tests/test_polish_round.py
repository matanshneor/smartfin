"""סבב ליטוש (מתן, 12.10): מטבעות לחיסכון, שורת מסקנה בהשוואה, מקלדת
מיידית באייפון, אייקוני קו בכפתורים, ובלי הקו הדק במצב כהה.

(הוצאות לפני הכנסות — ‎test_month_sections‎; "כמה נשאר" בפרויקטים —
‎test_project_list_and_deletion‎.)
"""
import datetime as dt
import re
from pathlib import Path

import pytest

from backend import supabase_config as db
from backend.icons import ui_icon

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_T = _ROOT / "frontend/templates"
_CSS = (_ROOT / "frontend/static/css/style.css").read_text(encoding="utf-8")
_TX = (_ROOT / "frontend/static/js/transactions.js").read_text(encoding="utf-8")


def _read(name):
    return (_T / name).read_text(encoding="utf-8")


# ─── 1 · מטבעות ולא שעון ─────────────────────────────────────────────────

def test_savings_is_coins_not_a_clock():
    home = _read("index.html")
    card = home[home.index('<a class="summary-card savings"'):]
    card = card[:card.index("</a>")]
    assert '<circle cx="8" cy="8" r="6"/>' in card
    assert '<polyline points="12 6 12 12 16 14"/>' not in home


# ─── 8 · שורת מסקנה ─────────────────────────────────────────────────────

def _t(month, expense, year=2026):
    return {"year": year, "month": month, "month_name": f"m{month}", "expense": float(expense),
            "income": 0.0, "savings": 0.0}


_TODAY = dt.date(2026, 10, 12)


def test_the_last_finished_month_against_the_three_before():
    trend = [_t(5, 9000), _t(6, 11200), _t(7, 10400), _t(8, 12900), _t(9, 11700), _t(10, 3000)]
    v = db.trend_verdict(trend, _TODAY)
    # ספטמבר — לא אוקטובר, שעוד לא נגמר; מול יוני–אוגוסט, לא מאי
    assert v == {"month_name": "m9", "expense": 11700.0, "avg": 11500.0, "count": 3,
                 "pct": 2, "direction": "same"}


def test_up_and_down():
    assert db.trend_verdict([_t(8, 10000), _t(9, 12000)], _TODAY)["direction"] == "up"
    v = db.trend_verdict([_t(7, 10000), _t(8, 10000), _t(9, 8000)], _TODAY)
    assert v["direction"] == "down" and v["pct"] == 20 and v["count"] == 2


def test_no_line_without_something_to_compare():
    assert db.trend_verdict([], _TODAY) is None
    assert db.trend_verdict([_t(9, 5000), _t(10, 100)], _TODAY) is None       # רק חודש אחד שנגמר
    assert db.trend_verdict([_t(8, 5000), _t(9, 0)], _TODAY) is None           # לא יצא כלום


def test_the_months_page_says_it_in_words():
    from backend.app import app
    v = {"month_name": "ספטמבר", "expense": 11700.0, "avg": 11500.0, "count": 3, "pct": 8, "direction": "up"}
    with app.test_request_context("/months"):
        html = app.jinja_env.get_template("months.html").render(
            active_page="months", user={"id": "x", "name": "מתן", "avatar_initial": "מ"},
            archive=[{"year": 2026, "month": 9, "income": 1.0, "expense": 1.0, "savings": 0.0, "balance": 0.0}], trend_data=[], cat_trend=None, member_series=None,
            today_year=2026, today_month=10, _HEBREW_MONTHS=[""] * 13, verdict=v)
    line = re.sub(r"\s+", " ", html[html.index('<p class="trend-verdict">'):])
    line = line[:line.index("</p>")]
    assert "בספטמבר הוצאתם <b>₪11,700</b>" in line
    assert '<b class="deficit">8% יותר</b> מהממוצע של 3 החודשים שלפניו' in line and "(₪11,500)" in line


# ─── 12 · המקלדת עולה מיד באייפון ────────────────────────────────────────

def test_adding_summons_the_keyboard_inside_the_tap():
    body = _TX[_TX.index("function openAddModal(presetType) {"):]
    head = body[:body.index("withLoadingTrigger(")]
    assert "summonKeyboard();" in head                    # לפני ההמתנה לטעינה
    fn = _TX[_TX.index("function summonKeyboard() {"):]
    fn = fn[:fn.index("\n    }\n")]
    assert "'(pointer: coarse)'" in fn and "setAttribute('inputmode', 'decimal')" in fn
    assert "font-size: 1rem" in _CSS[_CSS.index(".keyboard-proxy {"):]


def test_closing_does_not_bring_the_keyboard_back():
    open_ = _TX[_TX.index("function openModal() {"):]
    assert "document.activeElement === keyboardProxy\n            ? proxyReturnTo" in open_[:open_.index("\n    }\n")]


# ─── 13 · אייקוני קו ─────────────────────────────────────────────────────

def test_controls_are_line_icons_not_emoji():
    for name in ("base.html", "index.html", "month.html", "project_detail.html"):
        code = re.sub(r"\{#.*?#\}", "", _read(name), flags=re.S)
        for emoji in ("📷", "📎", "🔁"):
            assert emoji not in code, (name, emoji)
    assert '{{ ui_icon("camera") }}' in _read("base.html")
    assert '{{ ui_icon("calendar") }}' in _read("base.html")


def test_the_icon_takes_the_color_and_size_of_its_text():
    svg = str(ui_icon("receipt"))
    assert 'stroke="currentColor"' in svg and 'aria-hidden="true"' in svg
    assert ".ui-icon { width: 1em; height: 1em;" in _CSS


# ─── 14 · מצב כהה ───────────────────────────────────────────────────────

def test_dark_mode_drops_the_line_under_the_hero():
    assert ':root[data-theme="dark"] .page-hero { border-bottom-color: transparent; }' in _CSS


def test_reduced_motion_still_focuses_the_amount():
    """‎transition-duration: 0.01ms‎ הכללי השאיר את החלון ‎hidden‎ ברגע המיקוד —
    עם "הפחתת תנועה" הסמן נשאר על +. בדפדפן: נמדד, עכשיו ‎txAmount‎."""
    block = _CSS[_CSS.index("/* ─── Reduced motion"):]
    block = block[:block.index("\n}\n")]
    assert ".modal-overlay.open, .modal-overlay.open * { transition: none !important; }" in block
