"""סבב 4: "מה חדש" אחרי עדכון, ובן משפחה שהצטרף (מתן, 12.10)."""
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_JS = (_ROOT / "frontend/static/js/whats-new.js").read_text(encoding="utf-8")
_INDEX = (_ROOT / "frontend/templates/index.html").read_text(encoding="utf-8")


def test_whats_new_shows_once_per_version_and_not_to_new_families():
    assert "const VERSION = '" in _JS
    assert "page.dataset.newFamily === 'true'" in _JS
    assert "seen !== VERSION" in _JS


def test_the_home_page_carries_what_the_script_needs():
    assert 'id="sfHomeInfo"' in _INDEX and "(home_members or []) | tojson" in _INDEX
    assert 'id="memberJoined"' in _INDEX and "js/whats-new.js" in _INDEX


def test_member_joined_skips_me_and_the_first_visit_on_a_phone():
    assert "m.id !== page.dataset.me" in _JS
    assert "if (known === null) return;" in _JS
    assert "textContent" in _JS and "innerHTML" not in _JS      # שם בן משפחה — טקסט בלבד
