/* סכומי פרויקטים — מחושבים במסד במקום בפייתון.
 *
 * ‎_project_totals‎ משכה את *כל* עסקאות הפרויקטים של המשפחה, מאז ומתמיד,
 * בכל טעינה של עמוד ההגדרות והפרויקטים — וחיברה אותן בפייתון. בהיקף של
 * עשרות שורות זה מיידי; אחרי כמה שנים של טיולים ושיפוצים זו סריקה שגדלה
 * בלי גבול, על עמוד שנטען הרבה.
 *
 * ‎security invoker‎ ולא definer, בכוונה: RLS ממשיכה לחול, כך שהפונקציה
 * רואה בדיוק את מה שהקורא רשאי לראות. אין כאן שום סיבה לעקוף אותה.
 */
create or replace function public.project_totals(p_family_id uuid)
returns table(project_id uuid, expense numeric, income numeric, savings numeric)
language sql
stable
security invoker
set search_path = public
as $$
    select t.project_id,
           coalesce(sum(t.amount) filter (where t.type = 'expense'), 0),
           coalesce(sum(t.amount) filter (where t.type = 'income'),  0),
           coalesce(sum(t.amount) filter (where t.type = 'savings'), 0)
    from transactions t
    where t.family_id = p_family_id and t.project_id is not null
    group by t.project_id;
$$;

revoke all     on function public.project_totals(uuid) from public, anon;
grant  execute on function public.project_totals(uuid) to authenticated;
