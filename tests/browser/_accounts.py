"""חשבונות בדיקה זמניים לסקריפטי הדפדפן (מתן, 4.10).

כל סקריפט מייבא את המודול הזה בראשו. הייבוא יוצר שני חשבונות חדשים,
א' וב', כל אחד עם משפחה משלו, ושם את הפרטים שלהם בסביבה תחת השמות
שהסקריפטים כבר קוראים (‎RLS_TEST_EMAIL_A‎, ‎RLS_TEST_PASSWORD_A‎ וכו').
בסוף הריצה — גם אחרי חריגה — הם נמחקים עם כל מה שהשאירו. הסקריפטים
מריצים עזרי ‎.venv‎ בתהליכי-בן, והם יורשים את הסביבה ומקבלים את אותם
חשבונות.

היצירה והמחיקה עצמן ב-‎tests/_test_accounts.py‎, ורצות ב-‎.venv‎: הסקריפטים
רצים בפייתון של המערכת (שם מותקן Playwright), ושם אין את ספריית Supabase.
"""
import atexit
import json
import os
import subprocess

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_PY = os.path.join(_ROOT, ".venv", "bin", "python3")
_PRELUDE = ("import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'tests'); "
            "from dotenv import load_dotenv; load_dotenv('.env'); import _test_accounts as t; ")


def _venv(code: str) -> str:
    out = subprocess.run([_PY, "-c", _PRELUDE + code], cwd=_ROOT,
                         capture_output=True, text=True, timeout=180)
    if out.returncode != 0:
        raise RuntimeError(f"חשבונות הבדיקה הזמניים: {out.stderr[-600:]}")
    return out.stdout


if "RLS_TEST_PASSWORD_A" not in os.environ:
    _pair = json.loads(_venv("import json; print(json.dumps(t.create_pair('browser')))")
                       .strip().splitlines()[-1])
    for _key, _acc in _pair.items():
        os.environ[f"RLS_TEST_EMAIL_{_key.upper()}"] = _acc["email"]
        os.environ[f"RLS_TEST_PASSWORD_{_key.upper()}"] = _acc["password"]

    @atexit.register
    def _purge():
        ids = [a["user_id"] for a in _pair.values()]
        _venv(f"t.purge({ids!r})")
