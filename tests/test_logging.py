"""
בדיקות ללוגים.

הקוד השתמש ב-print בלבד — 61 קריאות, 44 מהן בתוך except. הפלט הלך לבאפר
הלוגים של Railway, שנמחק, ואף אחד לא קרא אותו. חשוב מכך: **Sentry לא ראה
אותו**. חובר ניטור שגיאות, ואז נותב סביבו מצב הכשל הנפוץ ביותר באפליקציה
— שאילתה שנכשלת ונבלעת.

עם logging, השילוב של Sentry עם מודול הלוגים תופס כל רשומת ERROR ומעלה
והופך אותה לאירוע. אותה שורת קוד, אבל עכשיו רואים אותה.
"""
import ast
import logging
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_BACKEND = Path(__file__).resolve().parent.parent / "backend"


def _sources():
    return [f for f in _BACKEND.glob("*.py") if f.name not in ("__init__.py", "logs.py")]


# ─── שום כשל לא נכתב יותר למקום שאף אחד לא קורא ─────────────────────────────

def test_nothing_in_the_backend_prints_any_more():
    offenders = []
    for f in _sources():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "print"):
                offenders.append(f"{f.name}:{node.lineno}")

    assert not offenders, f"print נשאר ב: {offenders} — Sentry לא יראה את זה"


def test_every_swallowed_exception_is_logged_with_its_traceback():
    """‎logger.exception‎ ולא ‎logger.error‎: הוא מצרף את ה-traceback, שהוא
    בדיוק מה שחסר כדי לדעת למה השאילתה נכשלה."""
    db = ast.parse((_BACKEND / "supabase_config.py").read_text(encoding="utf-8"))

    calls = [n for n in ast.walk(db)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "exception"]
    assert len(calls) >= 40, f"רק {len(calls)} — נראה שרוב הבליעות לא תועדו"


def test_no_exception_log_sits_outside_an_except_block():
    """‎logger.exception‎ מחוץ ל-except מדפיס "NoneType: None" במקום
    traceback — כלומר רשומה חסרת ערך בדיוק כשצריך אותה."""
    for f in _sources():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        bad = []

        class V(ast.NodeVisitor):
            def __init__(self): self.depth = 0
            def visit_ExceptHandler(self, node):
                self.depth += 1; self.generic_visit(node); self.depth -= 1
            def visit_Call(self, node):
                fn = node.func
                if (isinstance(fn, ast.Attribute) and fn.attr == "exception"
                        and isinstance(fn.value, ast.Name) and fn.value.id == "logger"
                        and self.depth == 0):
                    bad.append(node.lineno)
                self.generic_visit(node)

        V().visit(tree)
        assert not bad, f"{f.name}: logger.exception מחוץ ל-except בשורות {bad}"


# ─── שהלוג באמת יוצא ─────────────────────────────────────────────────────────

def test_a_failure_produces_a_record_with_the_traceback(caplog):
    from backend import supabase_config as db

    with caplog.at_level(logging.ERROR):
        try:
            raise RuntimeError("Supabase לא ענה")
        except Exception:
            db.logger.exception("get_monthly_summary")

    assert caplog.records, "לא נוצרה רשומה"
    record = caplog.records[0]
    assert record.levelno == logging.ERROR, "רמה נמוכה מ-ERROR לא הופכת לאירוע ב-Sentry"
    assert record.exc_info is not None, "אין traceback ברשומה"


def test_the_logger_is_configured_towards_stderr():
    """שם Railway אוסף. ‎force=True‎ כי gunicorn כבר נגע בהגדרות לפנינו,
    ובלעדיו ההגדרה נבלעת בשקט."""
    src = (_BACKEND / "logs.py").read_text(encoding="utf-8")

    assert "stream=sys.stderr" in src
    assert "force=True" in src


def test_noisy_libraries_are_quietened():
    """httpx מדווח כל בקשה ברמת INFO. בלי זה הלוג מוצף ואף אחד לא קורא
    אותו — כלומר חזרנו למצב שהתחלנו ממנו."""
    src = (_BACKEND / "logs.py").read_text(encoding="utf-8")

    assert "httpx" in src and "logging.WARNING" in src
