/* שתי פונקציות SECURITY DEFINER מקבלות מזהה משפחה ולא בודקות מי קורא.
 *
 * SECURITY DEFINER אומר שהפונקציה רצה בהרשאות של מי שיצר אותה ולא של מי
 * שקורא לה — כלומר RLS לא חלה עליה. זה נחוץ כאן (get_family_members קוראת
 * מ-auth.users, ש-RLS חוסמת), אבל המשמעות היא שהבדיקה חייבת להיות בתוך
 * הפונקציה. בשתי אלה היא פשוט לא הייתה:
 *
 *   get_family_members(uuid)  → שם, אימייל, טלפון ומקום עבודה של כל חברי
 *                                משפחה כלשהי, לפי מזהה
 *   get_months_archive(uuid)  → כל ההיסטוריה הכספית החודשית של משפחה כלשהי
 *
 * ובלי revoke, Postgres מעניק execute ל-PUBLIC כברירת מחדל — כלומר גם
 * ל-anon, בלי התחברות בכלל.
 *
 * מה שמגן כרגע הוא שהמפתח ל-PostgREST שמור בשרת ולא נחשף ללקוח. זו הגנה
 * אמיתית אבל יחידה, והיא לא מה שאמור להגן כאן. שאר הפונקציות בפרויקט כבר
 * עושות את זה נכון — join_family_by_code ו-delete_my_account נגזרות
 * מ-auth.uid() — ואלו שתי חריגות שנשכחו.
 *
 * הבדיקה משתמשת ב-get_my_family_id() שכבר קיים. מי שמבקש משפחה שאינו חבר
 * בה מקבל אפס שורות: זו התשובה הנכונה לשאלה על נתונים שאינם שלו.
 *
 * נוסף גם SET search_path — שתי אלה היו היחידות בלעדיו, וזה וקטור הסלמה
 * מוכר בפונקציות DEFINER.
 */

create or replace function public.get_family_members(p_family_id uuid)
returns table(id uuid, name text, avatar_initial text, email text, phone text, workplace text)
language sql
stable
security definer
set search_path = public
as $function$
    select p.id, p.name, p.avatar_initial, u.email::text, p.phone, p.workplace
    from profiles p
    join auth.users u on u.id = p.id
    where p.family_id = p_family_id
      and p_family_id = public.get_my_family_id()
    order by p.created_at;
$function$;

create or replace function public.get_months_archive(p_family_id uuid)
returns table(year integer, month integer, income numeric, expense numeric, savings numeric, balance numeric)
language sql
stable
security definer
set search_path = public
as $function$
    select
        extract(year  from date)::int  as year,
        extract(month from date)::int  as month,
        coalesce(sum(amount) filter (where type = 'income'),  0) as income,
        coalesce(sum(amount) filter (where type = 'expense'), 0) as expense,
        coalesce(sum(amount) filter (where type = 'savings'), 0) as savings,
        coalesce(sum(amount) filter (where type = 'income'),  0)
            - coalesce(sum(amount) filter (where type = 'expense'), 0) as balance
    from transactions
    where family_id = p_family_id
      and p_family_id = public.get_my_family_id()
      and project_id is null
    group by year, month
    order by year desc, month desc;
$function$;

revoke all     on function public.get_family_members(uuid) from public, anon;
revoke all     on function public.get_months_archive(uuid) from public, anon;
grant  execute on function public.get_family_members(uuid) to authenticated;
grant  execute on function public.get_months_archive(uuid) to authenticated;
