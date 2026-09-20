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


# ─── כשל שקט שמחזיר ערך שקרי ────────────────────────────────────────────────

# שתי בליעות שמותר להן להיות שקטות, ולמה:
#   _invalidate_family_cache — ‎except ImportError‎ סביב ייבוא של flask.
#     אין הקשר בקשה, אין מה לפנות. זו זרימת בקרה, לא כשל.
#   category_budget — ‎except (TypeError, ValueError)‎ על המרת ערך מתוך
#     ההגדרות. "אין תקציב לקטגוריה" היא תשובה נכונה לערך פגום, לא תקלה.
_MAY_STAY_SILENT = {"_invalidate_family_cache", "category_budget"}


def _enclosing_function(tree, node):
    best = None
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.lineno <= node.lineno <= (n.end_lineno or 0):
            if best is None or n.lineno > best.lineno:
                best = n
    return best.name if best else "?"


def test_no_failure_returns_a_falsy_answer_without_leaving_a_trace():
    """זו התבנית המסוכנת ביותר בקובץ הזה, וכבר עלתה ביוקר.

    פונקציה שנכשלת ומחזירה ‎None‎/‎False‎ נראית לקורא בדיוק כמו "אין
    נתון". גם כשהכיוון בטוח — לסרב, לא לאשר — המשתמש רואה משהו מבלבל
    ("הפרויקט לא נמצא", "אין קבלה"), ולמפתח אין שום דרך לחקור את זה
    אחר כך: הרשומה פשוט לא קיימת.
    """
    tree = ast.parse((_BACKEND / "supabase_config.py").read_text(encoding="utf-8"))
    falsy = {None, False, 0, "", ()}
    offenders = []

    for handler in ast.walk(tree):
        if not isinstance(handler, ast.ExceptHandler):
            continue
        body = ast.unparse(ast.Module(body=handler.body, type_ignores=[]))
        if "logger." in body or "raise" in body:
            continue
        for n in ast.walk(ast.Module(body=handler.body, type_ignores=[])):
            if not isinstance(n, ast.Return):
                continue
            v = n.value
            if v is None or (isinstance(v, ast.Constant) and v.value in falsy):
                name = _enclosing_function(tree, handler)
                if name not in _MAY_STAY_SILENT:
                    offenders.append(f"{name} (שורה {handler.lineno})")

    assert not offenders, (
        "בליעה שמחזירה ערך שקרי בלי לוג: " + ", ".join(sorted(set(offenders)))
    )
