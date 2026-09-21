/* מנהל המשפחה — האכיפה, ולא רק התג.
 *
 * התפקיד נוסף ב-20260916120000 ומיושם מאז לפעולה אחת בלבד: הסרת חבר.
 * כל שאר הפעולות ההרסניות נשארו פתוחות לכל מי שהצטרף עם קוד בן שישה
 * תווים — ובראשן איפוס העסקאות, שמוחק את היסטוריית **כל** המשפחה
 * ודורש רק את הסיסמה של מי שקורא לו.
 *
 * ובנוסף, פער ששיתק את התפקיד עצמו: delete_my_account נכתב חודשיים
 * לפני שנוסף manager_id, ומעולם לא עודכן. מנהל שמחק את חשבונו הותיר
 * ‎manager_id = NULL‎ (דרך ה-FK), ומאותו רגע remove_family_member נכשל
 * לתמיד — ‎NULL is distinct from <any uuid>‎ הוא תמיד אמת, ואין בשום
 * מקום קוד שמציב מנהל מחדש. המשפחה לא יכלה להסיר חבר לעולם.
 * leave_family כבר מעביר את הניהול; כאן אותו דבר בדיוק.
 */

-- ─── מי מנהל ─────────────────────────────────────────────────────────────────
-- ‎security definer‎ כדי שתקרא את families בלי תלות במדיניות הקריאה,
-- ומחזירה בוליאני בלבד — בלי לחשוף את מזהה המנהל למי שלא אמור לראותו.
create or replace function public.is_family_manager()
returns boolean
language sql
security definer
stable
set search_path = public
as $$
    select exists (
        select 1 from public.families f
         join public.profiles p on p.family_id = f.id
        where p.id = auth.uid() and f.manager_id = auth.uid()
    );
$$;

revoke all on function public.is_family_manager() from public, anon;
grant execute on function public.is_family_manager() to authenticated;


-- ─── מחיקת חשבון מעבירה את הניהול ────────────────────────────────────────────
create or replace function public.delete_my_account()
returns void
language plpgsql security definer set search_path = public as $$
declare
    v_uid    uuid := auth.uid();
    v_email  text;
    v_family uuid;
    v_others int  := 0;
    v_heir   uuid;
begin
    if v_uid is null then
        raise exception 'not authenticated';
    end if;

    select email into v_email from auth.users where id = v_uid;
    select family_id into v_family from public.profiles where id = v_uid;

    if v_family is not null then
        select count(*) into v_others from public.profiles
        where family_id = v_family and id <> v_uid;
    end if;

    -- ארכוב החשבון (כולל מייל) לפני המחיקה
    insert into public.owner_archive (kind, payload)
    select 'account',
           to_jsonb(p) || jsonb_build_object(
               'email', v_email,
               'was_last_member', (v_family is not null and v_others = 0))
    from public.profiles p where p.id = v_uid;

    -- החבר האחרון — ארכוב המשפחה (עם הקטגוריות והפרויקטים שלה) ומחיקתה
    if v_family is not null and v_others = 0 then
        insert into public.owner_archive (kind, payload)
        select 'family', jsonb_build_object(
            'family',     to_jsonb(f),
            'categories', (select coalesce(jsonb_agg(to_jsonb(c)), '[]'::jsonb)
                           from public.categories c where c.family_id = f.id),
            'projects',   (select coalesce(jsonb_agg(to_jsonb(pr)), '[]'::jsonb)
                           from public.projects pr where pr.family_id = f.id))
        from public.families f where f.id = v_family;

        delete from public.families where id = v_family;

    -- נשארו אחרים, והעוזב הוא המנהל: הניהול עובר לוותיק שנשאר. בלי
    -- השורות האלה המשפחה נתקעת בלי מנהל ולתמיד בלי יכולת להסיר חבר.
    elsif v_family is not null then
        if exists (select 1 from public.families
                    where id = v_family and manager_id = v_uid) then
            select p.id into v_heir from public.profiles p
              where p.family_id = v_family and p.id <> v_uid
              order by p.created_at limit 1;
            update public.families set manager_id = v_heir where id = v_family;
        end if;
    end if;

    -- מחיקה מ-auth מוחקת בשרשור את הפרופיל ומשחררת מייל + טלפון להרשמה חדשה
    delete from auth.users where id = v_uid;
end;
$$;
