/* עמוד ההגדרות בנסיעה אחת למסד (מתן, 13.10 — "הכי מהירה שאפשר").
 *
 * עד עכשיו: קטגוריות, ממוצע חודשי לכל קטגוריה, חברים, המשפחה, העסקאות
 * הקבועות, שתי שליפות ל"₪5,000 ← ₪5,500", ומספר העסקאות — זו אחרי זו,
 * ‎300-530ms‎ בלוגים. אחות של ‎get_month_page‎ ו-‎get_home_page‎, באותם
 * כללים: ההובלה כאן, החישובים נשארים ב-Python באותן פונקציות.
 *
 * (המייל העדכני מגיע משירות ההתחברות של Supabase ולא מהמסד — הוא נשאר
 * שליפה נפרדת.)
 *
 * SECURITY DEFINER עם הבדיקה ‎get_my_family_id()‎ — מי שמבקש משפחה שאינו
 * חבר בה מקבל ‎null‎.
 */

create or replace function public.get_settings_page(
    p_family_id uuid,
    p_avg_from  date,   -- שלושת החודשים השלמים האחרונים (‎category_monthly_averages‎)
    p_avg_to    date    -- לא כולל: תחילת החודש הנוכחי
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

        -- זהה ל-‎_fetch_categories‎
        'categories', coalesce((
            select jsonb_agg(to_jsonb(c) order by c.sort_order nulls last, c.name)
            from categories c
            where c.family_id is null or c.family_id = p_family_id
        ), '[]'::jsonb),

        -- הסכום לכל קטגוריה בחלון — החלוקה והעיגול ב-Python
        -- (‎category_averages_from_totals‎), כמו ב-‎category_monthly_averages‎
        'category_totals', coalesce((
            select jsonb_object_agg(x.category_id, x.total)
            from (
                select t.category_id::text as category_id, sum(t.amount) as total
                from transactions t
                where t.family_id = p_family_id
                  and t.project_id is null
                  and t.category_id is not null
                  and t.date >= p_avg_from
                  and t.date <  p_avg_to
                group by t.category_id
            ) x
        ), '{}'::jsonb),

        -- זהה ל-‎get_recurring_transactions‎: כל התבניות, מהגדולה לקטנה
        'recurring', coalesce((
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
                       ) order by t.amount desc
                   )
            from transactions t
            left join categories         c  on c.id  = t.category_id
            left join project_categories pc on pc.id = t.project_category_id
            left join profiles           pr on pr.id = t.user_id
            left join projects           pj on pj.id = t.project_id
            where t.family_id = p_family_id
              and t.is_recurring = true
        ), '[]'::jsonb),

        -- ל-‎recurring_price_changes‎: תבניות שהסתיימו...
        'ended', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'id', t.id, 'amount', t.amount, 'type', t.type,
                       'category_id', t.category_id, 'description', t.description,
                       'recurring_end_date', t.recurring_end_date))
            from transactions t
            where t.family_id = p_family_id
              and t.is_recurring = true
              and t.recurring_end_date is not null
        ), '[]'::jsonb),

        -- ...והסכום של המופע האחרון של כל אחת מהן
        'ended_last', coalesce((
            select jsonb_object_agg(x.parent, x.amount)
            from (
                select distinct on (i.recurring_parent_id)
                       i.recurring_parent_id::text as parent, i.amount
                from transactions i
                join transactions t on t.id = i.recurring_parent_id
                where i.family_id = p_family_id
                  and t.family_id = p_family_id
                  and t.is_recurring = true
                  and t.recurring_end_date is not null
                order by i.recurring_parent_id, i.date desc
            ) x
        ), '{}'::jsonb),

        -- זהה ל-‎family_transaction_count‎ — כולל פרויקטים ותבניות
        'transaction_count', (
            select count(*) from transactions t where t.family_id = p_family_id
        )
    )
    where p_family_id = public.get_my_family_id();
$function$;

revoke all     on function public.get_settings_page(uuid, date, date) from public, anon;
grant  execute on function public.get_settings_page(uuid, date, date) to authenticated;
