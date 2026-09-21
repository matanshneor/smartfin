"""
המסד לא היה ניתן לשחזור מהריפו.

‎get_my_family_id()‎ קיימת במסד, נקראת משתי מיגרציות שנדחפו
(‎20260916110000‎), מ-‎supabase_config.py‎, וממדיניות ה-RLS
‎profiles_family_read‎ — ולא היה לה שום ‎CREATE‎ בקבצים. היא נוצרה
דרך לוח הבקרה ומעולם לא נכתבה כמיגרציה.

בנייה מאפס מהקבצים נתנה סכימה שבה ‎get_family_members‎ ו-
‎get_months_archive‎ נכשלות — והראשונה בולעת את הכשל ומחזירה רשימה
ריקה, כלומר משפחה שמוצגת בלי אף חבר.

זה מחסיר בדיוק מהעבודה שסידרה את ספר המיגרציות ל-36/36: הפנקס היה
שלם, התוכן לא.

הבדיקה כאן לא בודקת את המסד — היא בודקת שהקבצים מספיקים לעצמם: כל
פונקציה ש-SQL בריפו קורא לה חייבת להיות מוגדרת ב-SQL בריפו.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_MIGRATIONS = Path(__file__).resolve().parent.parent / "backend/supabase/migrations"

# פונקציות של Postgres ושל Supabase עצמה — לא אמורות להיות מוגדרות אצלנו
_BUILTIN = {
    "auth", "count", "coalesce", "nullif", "btrim", "lower", "upper", "now",
    "gen_random_uuid", "gen_random_bytes", "date_trunc", "to_jsonb", "jsonb_build_object",
    "jsonb_agg", "array_length", "array_agg", "string_agg", "extract", "substr",
    "length", "floor", "random", "round", "sum", "min", "max", "exists", "set_config",
    "current_setting", "encode", "digest", "crypt", "gen_salt", "format", "concat",
    "trim", "replace", "position", "left", "right", "abs", "greatest", "least",
    "to_char", "age", "coalesce", "unnest", "generate_series", "row_to_json",
    "json_build_object", "make_date", "cast", "nextval", "currval", "setval",
}


def _sql():
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(_MIGRATIONS.glob("*.sql"))}


def _defined(all_sql):
    return set(re.findall(r"create (?:or replace )?function\s+(?:public\.)?([a-z_][a-z0-9_]*)",
                          all_sql, re.I))


def _tables(all_sql):
    return set(re.findall(r"create table (?:if not exists )?(?:public\.)?([a-z_][a-z0-9_]*)",
                          all_sql, re.I))


def _called(all_sql):
    """קריאות ל-‎public.<name>(‎ — בלי טבלאות.

    ‎insert into public.transactions (amount, ...)‎ נראה בדיוק כמו
    קריאה לפונקציה אם מסתכלים רק על שם ואחריו סוגר."""
    names = set(re.findall(r"public\.([a-z_][a-z0-9_]*)\s*\(", all_sql, re.I))
    return {n for n in names if n not in _tables(all_sql)}


def test_every_function_the_migrations_call_is_also_defined_there():
    """זה הכלל שהופר. מיגרציה שקוראת לפונקציה שלא מוגדרת בריפו הופכת
    את הריפו ללא-מספיק — והכשל מתגלה רק כשמישהו בונה מסד מאפס."""
    all_sql = "\n".join(_sql().values())
    missing = sorted(_called(all_sql) - _defined(all_sql) - _BUILTIN)

    assert not missing, f"נקראות ולא מוגדרות: {missing}"


def test_the_function_that_was_missing_is_there_now():
    all_sql = "\n".join(_sql().values())

    assert "get_my_family_id" in _defined(all_sql)


def test_it_is_defined_before_the_migrations_that_use_it():
    """סדר הקבצים הוא סדר ההרצה. פונקציה שנוצרת אחרי מי שקורא לה
    תיכשל בבנייה מאפס, גם אם שתיהן קיימות."""
    files = _sql()
    defined_in = next(n for n, s in files.items()
                      if re.search(r"create (?:or replace )?function\s+public\.get_my_family_id", s, re.I))
    callers = [n for n, s in files.items()
               if "public.get_my_family_id(" in s and n != defined_in]

    assert callers, "הבדיקה לא מצאה קוראים — כנראה השתנה הניסוח"
    late = [n for n in callers if n < defined_in]
    assert not late, (
        f"{defined_in} מוגדרת אחרי {late} — בנייה מאפס תיכשל שם, כי "
        f"Postgres מוודא גוף של פונקציית SQL בזמן היצירה")


def test_the_restored_definition_matches_what_the_database_has():
    """אומת ב-rollback מול המסד החי לפני הדחיפה: ההגדרה וההרשאות
    זהות בדיוק, כלומר המיגרציה היא תיעוד ולא שינוי."""
    sql = _sql()["20260916105900_get_my_family_id.sql"]

    assert "SELECT family_id FROM profiles WHERE id = auth.uid();" in sql
    assert "security definer" in sql.lower()
    assert "set search_path to 'public'" in sql.lower()
    assert "to authenticated, anon, service_role" in sql


def test_the_profiles_policy_is_not_the_recursive_version():
    """המדיניות בקבצים הייתה רקורסיבית: מדיניות SELECT על ‎profiles‎
    ששואלת את ‎profiles‎. בשרת היא מזמן עוברת דרך הפונקציה, שהיא
    ‎security definer‎ ולכן לא מפעילה את המדיניות שוב — אבל התיקון
    נשאר רק שם, ובנייה מהריפו הייתה מייצרת מדיניות שבורה."""
    files = _sql()
    fix = files["20260916105900_get_my_family_id.sql"]

    assert 'create policy "profiles_family_read"' in fix
    assert "public.get_my_family_id()" in fix
    # והיא באה אחרי הגרסה הרקורסיבית, אז היא דורסת אותה
    recursive = [n for n, s in files.items()
                 if 'CREATE POLICY "profiles_family_read"' in s]
    assert recursive and all(n < "20260916105900" for n in recursive)
