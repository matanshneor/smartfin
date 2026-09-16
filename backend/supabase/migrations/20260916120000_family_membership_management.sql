/* ניהול חברות במשפחה: הסרת חבר, עזיבה, והחלפת קוד הזמנה.
 *
 * עד היום מי שהצטרף למשפחה — בטעות, או עם קוד שדלף בוואטסאפ — נשאר בה
 * לתמיד. אין מסלול להסיר אותו, אין דרך לעזוב בעצמך, והקוד נוצר פעם אחת
 * ואי אפשר לשנותו. כלומר דליפה של שישה תווים היא גישה קבועה לכספי
 * המשפחה, למספרי הטלפון ולמקומות העבודה של כל חבריה.
 *
 * המודל היה שטוח לגמרי — כל החברים שווים. הסרה היא הפעולה הראשונה שדורשת
 * הבחנה, ולכן נוסף תפקיד אחד ויחיד: **מנהל המשפחה**. הוא יכול להסיר
 * אחרים; כל השאר הם בני משפחה רגילים שיכולים לעזוב בעצמם. את המנהל עצמו
 * אי אפשר להסיר — אחרת שני חברים היו יכולים להסיר זה את זה עד שלא נשאר
 * אף אחד. כשהוא עוזב, הניהול עובר לוותיק שנשאר.
 */

-- ─── מנהל המשפחה ───────────────────────────────────────────────────────────
alter table public.families
  add column if not exists manager_id uuid references public.profiles(id) on delete set null;

-- למשפחות קיימות: החבר הוותיק ביותר. זו לא ידיעה אלא ההערכה הטובה ביותר
-- שאפשר לגזור בדיעבד, והיא נכונה לכל משפחה שנפתחה דרך ensure_family.
update public.families f
   set manager_id = (select p.id from public.profiles p
                      where p.family_id = f.id order by p.created_at limit 1)
 where f.manager_id is null;

-- ─── יצירת משפחה מסמנת בעלות ───────────────────────────────────────────────
create or replace function public.create_own_family(p_name text default 'המשפחה שלי')
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    v_uid      uuid := auth.uid();
    v_existing uuid;
    v_id       uuid;
begin
    if v_uid is null then
        raise exception 'not authenticated';
    end if;

    select family_id into v_existing from public.profiles where id = v_uid;
    if v_existing is not null then
        return v_existing;
    end if;

    v_id := gen_random_uuid();
    insert into public.families (id, name, manager_id)
        values (v_id, coalesce(nullif(btrim(p_name), ''), 'המשפחה שלי'), v_uid);
    update public.profiles set family_id = v_id where id = v_uid;
    return v_id;
end;
$$;

-- ─── הסרת חבר (בעלים בלבד) ─────────────────────────────────────────────────
create or replace function public.remove_family_member(
    p_user_id uuid, p_keep_transactions boolean default true)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
    v_uid    uuid := auth.uid();
    v_family uuid;
    v_manager uuid;
    v_new    uuid;
begin
    if v_uid is null then raise exception 'not authenticated'; end if;
    if v_uid = p_user_id then raise exception 'use leave_family to remove yourself'; end if;

    select family_id into v_family from public.profiles where id = v_uid;
    if v_family is null then raise exception 'no family'; end if;

    select manager_id into v_manager from public.families where id = v_family;
    if v_manager is distinct from v_uid then raise exception 'only the family manager can remove members'; end if;
    if p_user_id = v_manager then raise exception 'the family manager cannot be removed'; end if;

    if not exists (select 1 from public.profiles
                    where id = p_user_id and family_id = v_family) then
        raise exception 'not a member of your family';
    end if;

    if p_keep_transactions then
        -- הכסף יצא מהתקציב המשותף, אז הסכומים נשארים נכונים. השיוך יורד
        -- והעסקה מוצגת כ"משותפת" — מצב שהתצוגה כבר יודעת להציג.
        update public.transactions set user_id = null
         where family_id = v_family and user_id = p_user_id;
    else
        -- הטריגר על transactions מארכב כל שורה בדרך החוצה
        delete from public.transactions
         where family_id = v_family and user_id = p_user_id;
    end if;

    -- משפחה חדשה וריקה, כדי שהחשבון שלו יישאר שמיש ולא ייתקע בלי משפחה
    v_new := gen_random_uuid();
    insert into public.families (id, name, manager_id) values (v_new, 'המשפחה שלי', p_user_id);
    update public.profiles set family_id = v_new where id = p_user_id;
end;
$$;

-- ─── עזיבה עצמית (כל אחד) ──────────────────────────────────────────────────
create or replace function public.leave_family(p_keep_transactions boolean default true)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    v_uid    uuid := auth.uid();
    v_family uuid;
    v_manager uuid;
    v_heir   uuid;
    v_new    uuid;
begin
    if v_uid is null then raise exception 'not authenticated'; end if;

    select family_id into v_family from public.profiles where id = v_uid;
    if v_family is null then raise exception 'no family'; end if;

    if p_keep_transactions then
        update public.transactions set user_id = null
         where family_id = v_family and user_id = v_uid;
    else
        delete from public.transactions
         where family_id = v_family and user_id = v_uid;
    end if;

    v_new := gen_random_uuid();
    insert into public.families (id, name, manager_id) values (v_new, 'המשפחה שלי', v_uid);
    update public.profiles set family_id = v_new where id = v_uid;

    select manager_id into v_manager from public.families where id = v_family;
    if v_manager = v_uid then
        -- הניהול עובר לוותיק שנשאר. בלי זה משפחה שהמנהל שלה עזב נשארת
        -- בלי אף אחד שיכול לנהל אותה.
        select p.id into v_heir from public.profiles p
          where p.family_id = v_family order by p.created_at limit 1;
        update public.families set manager_id = v_heir where id = v_family;
    end if;

    -- משפחה שנותרה ריקה ובלי היסטוריה היא זבל; עם היסטוריה היא נשמרת,
    -- בדיוק כמו ב-join_family_by_code.
    if not exists (select 1 from public.profiles where family_id = v_family)
       and not exists (select 1 from public.transactions where family_id = v_family) then
        delete from public.families where id = v_family;
    end if;

    return v_new;
end;
$$;

-- ─── החלפת קוד ההזמנה ──────────────────────────────────────────────────────
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

    -- כל בן משפחה רשאי, ולא רק המנהל: מי שמגלה שהקוד דלף צריך לסגור
    -- אותו מיד. הסיכון סימטרי — הקוד הישן מפסיק לעבוד, וזו כל המטרה.
    v_code := public.gen_invite_code();
    update public.families set invite_code = v_code where id = v_family;
    return v_code;
end;
$$;

revoke all on function public.remove_family_member(uuid, boolean) from public, anon;
revoke all on function public.leave_family(boolean)               from public, anon;
revoke all on function public.rotate_invite_code()                from public, anon;
grant execute on function public.remove_family_member(uuid, boolean) to authenticated;
grant execute on function public.leave_family(boolean)               to authenticated;
grant execute on function public.rotate_invite_code()                to authenticated;
