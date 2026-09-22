/* הצטרפות למשפחה אחרת נעלה את המשפחה שנעזבה, לנצח.
 *
 * ‎join_family_by_code‎ עדכנה ‎profiles.family_id‎ ולא נגעה ב-‎manager_id‎.
 * מי שפתח משפחה ואז הצטרף לאחרת השאיר את ‎families.manager_id‎ מצביע
 * עליו, בעוד הוא כבר לא חבר בה. ‎is_family_manager()‎ דורשת גם חברות וגם
 * התאמה, אז היא החזירה ‎false‎ **לכולם**:
 *
 *   - אי אפשר לאפס את עסקאות המשפחה
 *   - אי אפשר למחוק קטגוריה
 *   - אי אפשר להחליף קוד הזמנה שדלף
 *   - אי אפשר להסיר חבר
 *
 * ואין באפליקציה שום מסך שממנה מנהל חדש, כך שזה בלתי הפיך בלי גישה
 * ישירה למסד.
 *
 * ‎leave_family‎ ו-‎delete_my_account‎ שתיהן כבר מעבירות את התפקיד לוותיק
 * שנשאר. זו בדיוק אותה העברה, במסלול השלישי שפוספס.
 */
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

    -- הניהול עובר לוותיק שנשאר במשפחה הישנה. בלי זה היא נשארת עם מנהל
    -- שאינו חבר בה — כלומר בלי אף אחד שיכול לנהל אותה, לנצח.
    if v_old is not null then
        select manager_id into v_manager from public.families where id = v_old;
        if v_manager = v_uid then
            select p.id into v_heir from public.profiles p
              where p.family_id = v_old order by p.created_at limit 1;
            update public.families set manager_id = v_heir where id = v_old;
        end if;
    end if;

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

/* ותיקון למשפחות שכבר נתקעו ככה. אין דרך אחרת להחזיר להן ניהול. */
update public.families f
   set manager_id = (select p.id from public.profiles p
                      where p.family_id = f.id order by p.created_at limit 1)
 where f.manager_id is null
    or not exists (select 1 from public.profiles p
                    where p.id = f.manager_id and p.family_id = f.id);
