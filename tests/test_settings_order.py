"""סדר בהגדרות (מתן, 11.10): "זה שלי, או של המשפחה?"

עד אז השם ומקום העבודה נערכו מעיפרון ברשימת בני המשפחה, הצבע מכפתור באותה
שורה, ומייל, טלפון וסיסמה בקבוצה שלישית, "אבטחה וחשבון". עכשיו:
"החשבון שלי" — כל מה ששייך רק לי; "המשפחה שלי" — מה שמשותף, עם רשימת בני
משפחה לקריאה בלבד. הסדר: המשפחה ראשונה, אחריה לפי כמה נכנסים לכל קבוצה,
ו"החשבון שלי" אחרון, מעל "התנתקות".
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_HTML = (Path(__file__).resolve().parent.parent / "frontend/templates/settings.html").read_text(encoding="utf-8")


def _group(anchor):
    body = _HTML[_HTML.index(anchor):]
    return body[:body.index("</section>")]


def test_everything_of_mine_is_in_my_details():
    mine = _group('id="my-details"')
    for el in ("editProfileBtn", "memberColorOpen", "toggleEmailBtn", "togglePhoneBtn",
               "togglePasswordBtn", "toggleDeleteAccountBtn"):
        assert f'id="{el}"' in mine, el


def test_the_family_group_holds_what_is_shared():
    family = _group('id="family-settings"')
    for el in ("editFamilyNameBtn", "copyCodeBtn", "toggleFamilyMoveBtn",
               "toggleResetAccountBtn", "removeMemberBtn"):
        assert f'id="{el}"' in family, el
    # הרשימה לקריאה בלבד — בלי עריכה של הפרטים שלי מתוכה
    members = family[family.index('class="members-settings-list"'):]
    members = members[:members.index("</ul>")]
    assert "<button" not in members


def test_the_groups_come_in_matans_order():
    import re
    titles = re.findall(r'<span class="group-title">([^<]+)</span>', _HTML)
    assert titles == ["המשפחה שלי", "קטגוריות", "עסקאות קבועות", "העדפות משפחה",
                      "תצוגה", "החשבון שלי"]
    # "החשבון שלי" ממש מעל "התנתקות"
    assert _HTML.index('id="my-details"') < _HTML.index('class="logout-form') 
    assert '<span class="group-title">אבטחה וחשבון</span>' not in _HTML


def test_rare_actions_are_folded_away():
    """מחיקת חשבון, איפוס עסקאות והסרת בן משפחה — תחת "אפשרויות מתקדמות"."""
    for anchor, el in (('id="my-details"', "toggleDeleteAccountBtn"),
                       ('id="family-settings"', "toggleResetAccountBtn"),
                       ('id="family-settings"', "removeMemberBtn")):
        group = _group(anchor)
        folded = group[group.index('<details class="advanced-options">'):]
        assert f'id="{el}"' in folded, el
