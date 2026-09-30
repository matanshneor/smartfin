"""כל פעולה שכותבת נתונים מוגבלת בקצב (סקירה של 1.10).

ה-README הבטיח את זה, ו-13 פעולות לא היו מוגבלות — כל הפרויקטים, סידור
הקטגוריות, בדיקת הכפילות, סיום האשף. הבדיקה עוברת על כל המסלולים, כך
שמסלול חדש בלי הגבלה ייתפס מיד.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = (Path(__file__).resolve().parent.parent / "backend/app.py").read_text(encoding="utf-8")


def _routes():
    for m in re.finditer(r'^@app\.route\("([^"]+)"(?:, methods=\[([^\]]+)\])?\)', _SRC, re.M):
        head = _SRC[m.start():_SRC.index("\ndef ", m.start())]
        yield m.group(1), m.group(2) or '"GET"', head


def test_every_write_route_has_a_rate_limit():
    missing = [path for path, methods, head in _routes()
               if any(w in methods for w in ('"POST"', '"PUT"', '"DELETE"'))
               and "@limiter.limit(" not in head]
    assert not missing, missing
