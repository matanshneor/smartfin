/* עמוד החודש עשה חמש נסיעות למסד כדי לבנות מסך אחד.
 *
 * ‎_run_queries‎ (app.py) מריצה אותן ברצף בכוונה — היא הייתה מקבילית פעם,
 * והוחזרה לרצף אחרי ש"Server disconnected" מלקוח Supabase משותף החזיר
 * אפסים בשקט. כלומר החמש משלמות זו אחרי זו: ~30ms כל אחת, ~150ms סך הכל,
 * לפני שהתבנית התחילה להיבנות.
 *
 * הפתרון כאן הוא לא להריץ אותן מהר יותר אלא לא להריץ חמש. הפונקציה
 * מחזירה אובייקט אחד עם חמשת החלקים, וההרכבה נשארת ב-Python בדיוק כפי
 * שהייתה — ‎_merge_settings‎, קיצור שמות, ‎first_name‎ — כדי שהשינוי יהיה
 * בהובלה בלבד ולא בסמנטיקה.
 *
 * מבנה ה-‎rows‎ מחקה את מה ש-PostgREST החזיר עבור
 *   select("*, categories(name, icon), project_categories(name, icon),
 *           profiles(name, workplace), projects(owner_id, name, icon)")
 * כולל ‎null‎ (ולא ‎{}‎) כשאין שורה מקושרת — התבניות בודקות בדיוק את זה.
 *
 * SECURITY DEFINER כמו אחיותיה, ועם אותה בדיקה: ‎get_my_family_id()‎.
 * בלעדיה זו פונקציה שמוסרת את כל התמונה הכספית של משפחה כלשהי לפי מזהה.
 * מי שמבקש משפחה שאינו חבר בה מקבל ‎null‎, ו-Python מתייחס לזה ככשל שליפה.
 */

create or replace function public.get_month_page(
    p_family_id uuid,
    p_year      int,
    p_month     int
)
returns jsonb
language sql
stable
security definer
set search_path = public
as $function$
    select jsonb_build_object(

        -- שורת המשפחה במלואה: ‎settings‎ מתמזגת לברירות המחדל ב-Python,
        -- והשאר מזין את אותו מטמון-בקשה ש-‎get_family‎ היה ממלא.
        'family', (
            select to_jsonb(f) from families f where f.id = p_family_id
        ),

        -- זהה ל-get_family_members(uuid), כולל הסדר לפי הצטרפות: סדר
        -- החברים קובע את צבעי התגים (‎_member_colors‎), אז הוא לא קוסמטי.
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

        -- ‎family_id is null‎ הן הקטגוריות הגלובליות שנזרעות לכולם; בלעדיהן
        -- עמוד החודש מציג רק קטגוריות שהמשפחה הוסיפה בעצמה.
        'categories', coalesce((
            select jsonb_agg(to_jsonb(c) order by c.sort_order nulls last, c.name)
            from categories c
            where c.family_id is null or c.family_id = p_family_id
        ), '[]'::jsonb),

        -- כולל עסקאות פרויקט. ההחרגה נעשית במעלה הזרם (‎_household_rows‎),
        -- והשליפה הזאת היא המקור לשתי התמונות גם יחד.
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

        -- זהה ל-get_months_archive(uuid): רצועת החודשים בראש העמוד.
        'archive', coalesce((
            select jsonb_agg(jsonb_build_object(
                       'year',    a.year,    'month',   a.month,
                       'income',  a.income,  'expense', a.expense,
                       'savings', a.savings, 'balance', a.balance
                   ) order by a.year desc, a.month desc)
            from (
                select extract(year  from date)::int as year,
                       extract(month from date)::int as month,
                       coalesce(sum(amount) filter (where type = 'income'),  0) as income,
                       coalesce(sum(amount) filter (where type = 'expense'), 0) as expense,
                       coalesce(sum(amount) filter (where type = 'savings'), 0) as savings,
                       coalesce(sum(amount) filter (where type = 'income'),  0)
                           - coalesce(sum(amount) filter (where type = 'expense'), 0) as balance
                from transactions
                where family_id = p_family_id
                  and project_id is null
                group by 1, 2
            ) a
        ), '[]'::jsonb)
    )
    -- אפס שורות → הפונקציה מחזירה null. זו התשובה הנכונה לשאלה על משפחה
    -- שאינה שלך, והיא גם מה ש-Python מזהה ככשל ולא כ"משפחה ריקה".
    where p_family_id = public.get_my_family_id();
$function$;

revoke all     on function public.get_month_page(uuid, int, int) from public, anon;
grant  execute on function public.get_month_page(uuid, int, int) to authenticated;
