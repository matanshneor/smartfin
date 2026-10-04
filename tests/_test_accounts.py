"""חשבונות בדיקה זמניים (מתן, 4.10: "משפחות הבדיקה לא אמורות להיות חלק ממסד הנתונים").

כל ריצה — של pytest או של סקריפט דפדפן — יוצרת לעצמה שני משתמשים, כל אחד
עם משפחה משלו, ומוחקת את שניהם בסוף, יחד עם כל מה שהם השאירו: העסקאות,
הקטגוריות, הפרויקטים, הארכיון הפנימי (‎owner_archive‎ — טריגר מארכב כל
עסקה שנמחקת, וזה המקום שבו הצטברו 14,500 שורות בדיקה), יומן הכניסות
וסריקות הקבלות.

עד 4.10 היו שני משתמשי בדיקה קבועים במסד הייצור, והם נספרו בכל מסך ניהול.

היצירה והמחיקה רצות ב-SQL בהרשאות בעלים, דרך ה-CLI המקושר — כמו הקמת
המצב ב-‎test_family_join‎. לא דרך ‎sign_up‎: ל-Supabase יש מכסת הרשמות
והתחברויות לכתובת IP, וסדרת סקריפטי דפדפן הייתה נתקעת בה. ההתחברות
עצמה היא התחברות רגילה, כמו של כל משתמש.

ריצה שנקטעה באמצע (Ctrl+C, קריסה) לא מספיקה למחוק. לכן כל יצירה מתחילה
בניקוי של חשבונות בדיקה שנשארו מריצות קודמות — רק כאלה שנוצרו לפני
יותר משעתיים, כדי לא למחוק חשבונות של ריצה שרצה עכשיו במקביל.
"""
import os
import secrets
import subprocess
import uuid

_BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")

# ‎.test‎ הוא דומיין שמור (RFC 2606). אבל הניקוי **לא** מזהה חשבון בדיקה לפי
# המייל: ההרשמה לא מאמתת מייל, אז כל אחד יכול להירשם עם הדומיין הזה. הסימן
# הוא ‎app_metadata.smartfin_test‎ — שדה שרק השרת כותב; ‎sign_up‎ של לקוח
# כותב ל-‎user_metadata‎ בלבד.
DOMAIN = "smartfin.test"
_MARK = "raw_app_meta_data->>'smartfin_test' = 'true'"
_STALE = "2 hours"


def privileged_sql(sql: str) -> str:
    """SQL בהרשאות בעלים, דרך ה-CLI המקושר. זורקת אם נכשל."""
    out = subprocess.run(["supabase", "db", "query", sql, "--linked"],
                         cwd=_BACKEND, capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f"SQL בהרשאות בעלים נכשל: {out.stderr[-400:]}")
    return out.stdout


def _q(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create_pair(label: str = "run") -> dict:
    """שני משתמשים חדשים, א' וב', כל אחד עם משפחה משלו.

    מחזירה ‎{"a": {"email", "password", "user_id", "family_id", "token"}, "b": …}‎."""
    from backend import supabase_config as db

    sweep_stale()
    run = uuid.uuid4().hex[:8]
    accounts = {}
    for key in ("a", "b"):
        accounts[key] = {"user_id": str(uuid.uuid4()),
                         "email": f"test-{label}-{run}-{key}@{DOMAIN}",
                         "password": secrets.token_urlsafe(18),
                         "name": f"בדיקה {key.upper()}"}
    privileged_sql("".join(f"""
        insert into auth.users (instance_id, id, aud, role, email, encrypted_password,
            email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
            confirmation_token, recovery_token, email_change_token_new, email_change)
        values ('00000000-0000-0000-0000-000000000000', {_q(a['user_id'])}, 'authenticated',
            'authenticated', {_q(a['email'])},
            extensions.crypt({_q(a['password'])}, extensions.gen_salt('bf')), now(),
            '{{"provider":"email","providers":["email"],"smartfin_test":true}}',
            jsonb_build_object('name', {_q(a['name'])}), now(), now(), '', '', '', '');
        insert into auth.identities (provider_id, user_id, identity_data, provider,
            created_at, updated_at, last_sign_in_at)
        values ({_q(a['user_id'])}, {_q(a['user_id'])},
            jsonb_build_object('sub', {_q(a['user_id'])}, 'email', {_q(a['email'])},
                               'email_verified', true),
            'email', now(), now(), now());""" for a in accounts.values()))

    try:
        for key, a in accounts.items():
            # התחברות ראשונה רגילה — ‎ensure_family‎ פותחת את המשפחה, כמו
            # לכל משתמש חדש באפליקציה
            response, err = db.sign_in(a["email"], a["password"])
            if err:
                raise RuntimeError(f"התחברות לחשבון בדיקה חדש נכשלה ({a['email']}): {err}")
            db.set_auth_token(response.session.access_token)
            a["family_id"] = db.ensure_family(a["user_id"], f"משפחת בדיקה {key.upper()}")
            if not a["family_id"]:
                raise RuntimeError(f"לא נפתחה משפחה לחשבון בדיקה {a['email']}")
            # ואשף הפתיחה, עם קטגוריות ברירת המחדל — משפחה בלי קטגוריות
            # נשלחת ל-‎/onboarding‎ מכל עמוד, ואי אפשר להזין בה עסקה
            from backend.app import _DEFAULT_CATEGORIES
            _, err = db.bulk_add_categories(a["family_id"], _DEFAULT_CATEGORIES)
            if err:
                raise RuntimeError(f"קטגוריות לחשבון בדיקה {a['email']}: {err}")
            a["token"] = response.session.access_token
    except Exception:
        purge([a["user_id"] for a in accounts.values()])
        raise
    return accounts


def _purge_sql(users_where: str, extra_family_ids=()) -> str:
    """מוחקת את המשתמשים שעונים לתנאי, את המשפחות שלהם וכל עקבה.

    הסדר חשוב: מחיקת המשפחה מוחקת בשרשור את העסקאות, והטריגר מארכב כל
    אחת מהן — אז הארכיון מנוקה **אחרי** מחיקת המשפחות. ‎_tf‎ נבנית מראש,
    כי אחרי מחיקת המשתמשים אין יותר דרך לדעת מה היו המשפחות שלהם.

    ‎extra_family_ids‎ — משפחות זמניות בלי חברים (‎test_family_join‎)."""
    extra = ", ".join(f"({_q(f)}::uuid)" for f in extra_family_ids)
    return f"""
        begin;
        create temp table _tu on commit drop as
            select id from auth.users where {users_where};
        create temp table _tf on commit drop as
            select distinct family_id as id from public.profiles
            where id in (select id from _tu) and family_id is not null
            {"union select column1 from (values " + extra + ") v" if extra else ""};
        -- משפחה שגם חבר אמיתי שייך אליה לא נמחקת, אף פעם
        delete from _tf where id in (
            select family_id from public.profiles
            where family_id is not null and id not in (select id from _tu));
        delete from public.families where id in (select id from _tf);
        delete from public.owner_archive
            where (kind = 'transaction' and (payload->>'family_id')::uuid in (select id from _tf))
               or (kind = 'family' and (payload->'family'->>'id')::uuid in (select id from _tf))
               or (kind = 'account' and (payload->>'id')::uuid in (select id from _tu));
        delete from public.login_events where user_id in (select id from _tu);
        delete from auth.users where id in (select id from _tu);
        commit;
    """


def purge(user_ids, extra_family_ids=()) -> None:
    """מוחקת את חשבונות הבדיקה האלה וכל מה שהשאירו. רק חשבונות שנוצרו כאן."""
    ids = ", ".join(f"{_q(u)}::uuid" for u in user_ids)
    if not ids and not extra_family_ids:
        return
    where = f"id in ({ids or 'null'}) and {_MARK}"
    privileged_sql(_purge_sql(where, extra_family_ids))


def sweep_stale() -> None:
    """חשבונות בדיקה שנשארו מריצה שנקטעה — כל מה שנוצר כאן לפני יותר
    משעתיים."""
    privileged_sql(_purge_sql(f"{_MARK} and created_at < now() - interval '{_STALE}'"))
