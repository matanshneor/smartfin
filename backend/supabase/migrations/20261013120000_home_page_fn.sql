/* דף הבית בנסיעה אחת למסד (מתן, 13.10 — "הכי מהירה שאפשר").
 *
 * עד עכשיו דף הבית שלח תשע שאלות, זו אחרי זו (ראו ‎_run_queries‎ ב-app.py
 * על למה ברצף): הגדרות, סיכום החודש, קטגוריות, חברים, "משפחה חדשה?",
 * עסקאות אחרונות, השבוע, "יש שבוע קודם?", ושורות החודש להתראות. בלוגים:
 * ‎300-400ms‎ ברגיל. עמוד החודש עבר לפונקציה אחת (‎get_month_page‎) ולוקח
 * ‎40-90ms‎.
 *
 * כמו שם: ההובלה בלבד עוברת לכאן. החישובים (סיכום, השבוע, התראות, עיצוב
 * העסקאות) נשארים ב-Python, באותן פונקציות בדיוק, כדי שלא יהיו שני מקורות
 * אמת. כל חלק כאן מחקה את השאילתה שהוא מחליף — כולל ‎null‎ ולא ‎{}‎ כשאין
 * שורה מקושרת, כי התבניות בודקות בדיוק את זה.
 *
 * התאריכים מחושבים ב-Python ונשלחים (‎clock.today()‎ — שעון ישראל), ולא
 * ‎current_date‎ של המסד שרץ ב-UTC: בין חצות לשלוש לפנות בוקר היו שני
 * "היום" שונים.
 *
 * SECURITY DEFINER עם אותה בדיקה כמו ‎get_month_page‎: ‎get_my_family_id()‎.
 * מי שמבקש משפחה שאינו חבר בה מקבל ‎null‎.
 */

create or replace function public.get_home_page(
    p_family_id     uuid,
    p_year          int,
    p_month         int,
    p_recent_from   date,   -- תחילת החודש: עסקאות מסדרה קבועה רק מכאן (‎_recent_series_filter‎)
    p_recent_limit  int,
    p_week_from     date,   -- ראשון של השבוע הקודם
    p_week_start    date,   -- ראשון של השבוע המוצג
    p_week_to       date    -- שבת של השבוע המוצג
)
returns jsonb
language sql
stable
security definer
set search_path = public
as $function$
    select jsonb_build_object(

        'family', (
            select to_jsonb(f) from families f where f.id = p_family_id
        ),

        -- זהה ל-‎get_month_page‎ / ‎get_family_members(uuid)‎, כולל הסדר
        'members', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'id',             p.id,
                       'name',           p.name,
                       'avatar_initial', p.avatar_initial,
                       'email',          u.email::text,
                       'phone',          p.phone,
                       'workplace',      p.workplace
                   ) order by p.created_at)
            from profiles p
            join auth.users u on u.id = p.id
            where p.family_id = p_family_id
        ), '[]'::jsonb),

        -- זהה ל-‎_fetch_categories‎: ‎sort_order‎ (ריקים בסוף), ואז שם
        'categories', coalesce((
            select jsonb_agg(to_jsonb(c) order by c.sort_order nulls last, c.name)
            from categories c
            where c.family_id is null or c.family_id = p_family_id
        ), '[]'::jsonb),

        -- זהה ל-‎fetch_month_rows‎: כל שורות החודש, כולל פרויקטים. ממנו
        -- נגזרים גם סיכום החודש (בלי פרויקטים) וגם התראות התקציב.
        'rows', coalesce((
            select jsonb_agg(
                       to_jsonb(t) || jsonb_build_object(
                           'categories', case when c.id is null then null
                               else jsonb_build_object('name', c.name, 'icon', c.icon) end,
                           'project_categories', case when pc.id is null then null
                               else jsonb_build_object('name', pc.name, 'icon', pc.icon) end,
                           'profiles', case when pr.id is null then null
                               else jsonb_build_object('name', pr.name, 'workplace', pr.workplace) end,
                           'projects', case when pj.id is null then null
                               else jsonb_build_object('owner_id', pj.owner_id,
                                                       'name', pj.name, 'icon', pj.icon) end
                       ) order by t.date desc
                   )
            from transactions t
            left join categories         c  on c.id  = t.category_id
            left join project_categories pc on pc.id = t.project_category_id
            left join profiles           pr on pr.id = t.user_id
            left join projects           pj on pj.id = t.project_id
            where t.family_id = p_family_id
              and t.date >= make_date(p_year, p_month, 1)
              and t.date <  make_date(p_year, p_month, 1) + interval '1 month'
        ), '[]'::jsonb),

        -- זהה ל-‎get_recent_transactions‎: בלי פרויקטים, לפי סדר ההזנה,
        -- ועסקאות מסדרה קבועה רק מתחילת החודש
        'recent', coalesce((
            select jsonb_agg(r.j order by r.created_at desc)
            from (
                select t.created_at,
                       to_jsonb(t) || jsonb_build_object(
                           'categories', case when c.id is null then null
                               else jsonb_build_object('name', c.name, 'icon', c.icon) end,
                           'project_categories', case when pc.id is null then null
                               else jsonb_build_object('name', pc.name, 'icon', pc.icon) end,
                           'profiles', case when pr.id is null then null
                               else jsonb_build_object('name', pr.name, 'workplace', pr.workplace) end,
                           'projects', null
                       ) as j
                from transactions t
                left join categories         c  on c.id  = t.category_id
                left join project_categories pc on pc.id = t.project_category_id
                left join profiles           pr on pr.id = t.user_id
                where t.family_id = p_family_id
                  and t.project_id is null
                  and ((t.is_recurring is not true and t.recurring_parent_id is null)
                       or t.date >= p_recent_from)
                order by t.created_at desc
                limit p_recent_limit
            ) r
        ), '[]'::jsonb),

        -- זהה ל-‎week_spending‎: הוצאות הבית של השבוע הקודם והנוכחי
        'week_rows', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'amount',              t.amount,
                       'date',                t.date,
                       'description',         t.description,
                       'category_id',         t.category_id,
                       'is_recurring',        t.is_recurring,
                       'recurring_parent_id', t.recurring_parent_id,
                       'project_id',          t.project_id,
                       'categories', case when c.id is null then null
                           else jsonb_build_object('name', c.name, 'icon', c.icon) end
                   ))
            from transactions t
            left join categories c on c.id = t.category_id
            where t.family_id = p_family_id
              and t.type = 'expense'
              and t.project_id is null
              and t.date >= p_week_from
              and t.date <= p_week_to
        ), '[]'::jsonb),

        -- "יש לאן לדפדף אחורה" — ‎is_recurring = false‎ בדיוק כמו ‎.eq(False)‎
        -- שם (שורה עם ‎NULL‎ לא נספרת)
        'week_has_older', exists (
            select 1 from transactions t
            where t.family_id = p_family_id
              and t.type = 'expense'
              and t.project_id is null
              and t.is_recurring = false
              and t.recurring_parent_id is null
              and t.date < p_week_start
        ),

        -- "משפחה חדשה" — אף עסקה מעולם, כולל פרויקטים
        'has_transactions', exists (
            select 1 from transactions t where t.family_id = p_family_id
        )
    )
    where p_family_id = public.get_my_family_id();
$function$;

revoke all     on function public.get_home_page(uuid, int, int, date, int, date, date, date) from public, anon;
grant  execute on function public.get_home_page(uuid, int, int, date, int, date, date, date) to authenticated;
