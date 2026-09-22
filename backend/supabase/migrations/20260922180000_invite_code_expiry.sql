/* קוד ההזמנה היה מפתח קבוע, ל-32^6 אפשרויות, שלא פג לעולם.
 *
 * ‎32^6 ≈ 2^30‎ — בערך מיליארד. זה סביר לקוד בן שישה תווים שאנשים
 * מקריאים בטלפון, וזה **לא** סביר כשהוא תקף לנצח: מי שקיבל אותו פעם
 * אחת נכנס איתו תמיד, גם שנה אחרי שעזב, וההגנה היחידה מפני ניחוש
 * שיטתי היא הגבלת קצב ב-Flask — שנחלשת בשקט אם ‎RATELIMIT_STORAGE_URI‎
 * חסר.
 *
 * וקוד תקף פירושו קריאה **וכתיבה** מלאות על כל ההיסטוריה הפיננסית של
 * המשפחה, ועל השם, האימייל, הטלפון ומקום העבודה של כל חבר בה.
 *
 * תפוגה הופכת את החשבון הזה ללא רלוונטי: 7 ימים הם מספיק זמן לשלוח
 * קוד בוואטסאפ ולחכות שמישהו יתפנה, וקצרים מכדי שסריקה תספיק לפגוע
 * בחלון.
 *
 * ההגדרות מציגות מתי הקוד פג, ולמנהל יש שם כפתור להפיק חדש — אותה
 * פעולה שכבר הייתה קיימת, עכשיו עם סיבה גלויה להשתמש בה.
 */
alter table public.families
    add column if not exists invite_code_expires_at timestamptz;

-- הקודים הקיימים מקבלים חלון מלא מרגע המיגרציה, ולא פגים מיד.
update public.families
   set invite_code_expires_at = now() + interval '7 days'
 where invite_code_expires_at is null;

create or replace function public.rotate_invite_code()
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
    v_uid    uuid := auth.uid();
    v_family uuid;
    v_code   text;
begin
    if v_uid is null then raise exception 'not authenticated'; end if;

    select family_id into v_family from public.profiles where id = v_uid;
    if v_family is null then raise exception 'no family'; end if;

    if not exists (select 1 from public.families
                    where id = v_family and manager_id = v_uid) then
        raise exception 'only the family manager can rotate the invite code';
    end if;

    v_code := public.gen_invite_code();
    update public.families
       set invite_code            = v_code,
           invite_code_expires_at = now() + interval '7 days'
     where id = v_family;
    return v_code;
end;
$$;

/* ‎join_family_by_code‎ מכבדת את התפוגה. קוד שפג נראה בדיוק כמו קוד
 * שגוי — אחרת התשובה עצמה מגלה שהקוד הזה היה אמיתי פעם, וזה בדיוק
 * המידע שמנחש מחפש. */
create or replace function public.join_family_by_code(p_code text)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    v_uid     uuid := auth.uid();
    v_code    text;
    v_family  uuid;
    v_old     uuid;
    v_manager uuid;
    v_heir    uuid;
begin
    if v_uid is null then
        raise exception 'not authenticated';
    end if;

    v_code := upper(regexp_replace(coalesce(p_code, ''), '[^A-Za-z0-9]', '', 'g'));
    if v_code = '' then
        return null;
    end if;

    select id into v_family from public.families
     where invite_code = v_code
       and (invite_code_expires_at is null or invite_code_expires_at > now());
    if v_family is null then
        return null;
    end if;

    select family_id into v_old from public.profiles where id = v_uid;
    if v_old = v_family then
        return v_family;
    end if;

    update public.profiles set family_id = v_family where id = v_uid;

    -- הניהול עובר לוותיק שנשאר במשפחה הישנה (ראו 20260922130000).
    if v_old is not null then
        select manager_id into v_manager from public.families where id = v_old;
        if v_manager = v_uid then
            select p.id into v_heir from public.profiles p
              where p.family_id = v_old order by p.created_at limit 1;
            update public.families set manager_id = v_heir where id = v_old;
        end if;
    end if;

    if v_old is not null
       and not exists (select 1 from public.profiles where family_id = v_old)
       and not exists (select 1 from public.transactions where family_id = v_old)
    then
        delete from public.families where id = v_old;
    end if;

    return v_family;
end;
$$;

/* ותצוגה מקדימה: קוד שפג לא מחזיר שם משפחה. */
create or replace function public.family_name_for_code(p_code text)
returns text
language sql
security definer
stable
set search_path = public
as $$
    select f.name from public.families f
     where f.invite_code = upper(regexp_replace(coalesce(p_code, ''), '[^A-Za-z0-9]', '', 'g'))
       and (f.invite_code_expires_at is null or f.invite_code_expires_at > now());
$$;

grant execute on function public.join_family_by_code(text)  to authenticated;
grant execute on function public.rotate_invite_code()       to authenticated;
revoke all on function public.rotate_invite_code()          from public, anon;
grant execute on function public.family_name_for_code(text) to anon, authenticated;
