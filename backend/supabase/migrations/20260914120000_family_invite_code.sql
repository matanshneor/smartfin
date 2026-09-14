-- קוד הזמנה קצר למשפחה + הצטרפות שעובדת.
--
-- הרקע: עד היום קוד ההזמנה היה ה-UUID של המשפחה, ו-join_family_by_code בצד
-- Python וידא שהמשפחה קיימת ב-SELECT רגיל על families. אבל מדיניות ה-RLS
-- families_member_read מתירה לקרוא משפחה רק למי שכבר חבר בה — ומשתמש חדש
-- שנרשם עם קוד עדיין לא חבר באף משפחה. לכן ה-SELECT תמיד חזר ריק וההצטרפות
-- נכשלה בשקט, בכל פעם מאז שהפיצ'ר נכתב. המשתמש קיבל "נרשמת בהצלחה" ואז
-- ensure_family פתח לו משפחה חדשה משלו.
--
-- התיקון: פונקציית RPC עם security definer, שרצה בהרשאות הבעלים ולכן רואה
-- את הטבלה במלואה — אותו דפוס כמו email_for_phone ו-delete_my_account.
-- בנוסף הקוד עובר מ-UUID בן 36 תווים לקוד בן 6 תווים שאפשר להקריא בטלפון.

-- ─── קוד הזמנה ───────────────────────────────────────────────────────────────

alter table public.families add column if not exists invite_code text;

-- אלפבית ללא תווים מתבלבלים: אין I/1 ואין O/0, כדי שהקראה בטלפון לא תיכשל.
create or replace function public.gen_invite_code()
returns text
language plpgsql
set search_path = public
as $$
declare
    v_alphabet constant text := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    v_code text;
    v_i    int;
begin
    loop
        v_code := '';
        for v_i in 1..6 loop
            v_code := v_code || substr(
                v_alphabet, 1 + floor(random() * length(v_alphabet))::int, 1);
        end loop;
        exit when not exists (
            select 1 from public.families where invite_code = v_code);
    end loop;
    return v_code;
end;
$$;

-- בקפילינג שורה-שורה ולא ב-UPDATE אחד: בתוך statement יחיד תת-השאילתה שבודקת
-- ייחודיות לא רואה שורות שאותו statement עצמו עדכן, ושתי משפחות היו עלולות
-- לקבל את אותו קוד. לולאה עם statement נפרד לכל שורה מונעת את זה.
do $$
declare
    r record;
begin
    for r in select id from public.families where invite_code is null loop
        update public.families
           set invite_code = public.gen_invite_code()
         where id = r.id;
    end loop;
end $$;

create unique index if not exists families_invite_code_unique_idx
    on public.families (invite_code);

alter table public.families alter column invite_code set not null;
alter table public.families alter column invite_code set default public.gen_invite_code();

-- ─── הצטרפות למשפחה ─────────────────────────────────────────────────────────

-- מחזירה את ה-family_id בהצלחה, ו-NULL כשהקוד לא קיים — כדי שהשכבה שמעל
-- תוכל להבחין בין "הצטרפת" לבין "הקוד שגוי" במקום לבלוע את שניהם.
create or replace function public.join_family_by_code(p_code text)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    v_uid    uuid := auth.uid();
    v_code   text;
    v_family uuid;
    v_old    uuid;
begin
    if v_uid is null then
        raise exception 'not authenticated';
    end if;

    -- נרמול הקלט: הקוד עובר בוואטסאפ ובהקראה בטלפון, אז מסירים כל מה שאינו
    -- אות או ספרה (רווחים, מקפים, תווי כיווניות) ומיישרים לאותיות גדולות.
    v_code := upper(regexp_replace(coalesce(p_code, ''), '[^A-Za-z0-9]', '', 'g'));
    if v_code = '' then
        return null;
    end if;

    select id into v_family from public.families where invite_code = v_code;
    if v_family is null then
        return null;
    end if;

    select family_id into v_old from public.profiles where id = v_uid;
    if v_old = v_family then
        return v_family;  -- כבר חבר שם, אין מה לעשות
    end if;

    update public.profiles set family_id = v_family where id = v_uid;

    -- ניקוי המשפחה הנטושה. בכניסה הראשונה ensure_family פותח לכל משתמש
    -- משפחה משלו, ובלי הניקוי הזה כל הצטרפות הייתה משאירה אחריה משפחה ריקה
    -- בשם "המשפחה שלי" — בדיוק הזבל שהצטבר בטבלה עד היום. מוחקים רק כשאין
    -- בה אף חבר אחר ואף תנועה, כדי שלעולם לא תאבד היסטוריה אמיתית.
    if v_old is not null
       and not exists (select 1 from public.profiles where family_id = v_old)
       and not exists (select 1 from public.transactions where family_id = v_old)
    then
        delete from public.families where id = v_old;
    end if;

    return v_family;
end;
$$;

grant execute on function public.join_family_by_code(text) to authenticated;

-- תצוגה מקדימה לפני האישור ("מצטרפים למשפחת כהן?"). מחזירה רק את השם, ולא
-- חושפת שום דבר אחר על המשפחה.
create or replace function public.family_name_for_code(p_code text)
returns text
language sql
security definer
set search_path = public
stable
as $$
    select name
    from public.families
    where invite_code = upper(regexp_replace(coalesce(p_code, ''), '[^A-Za-z0-9]', '', 'g'))
    limit 1;
$$;

grant execute on function public.family_name_for_code(text) to anon, authenticated;
