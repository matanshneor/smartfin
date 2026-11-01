/* דילוג על חודש עתידי בסדרה קבועה (מתן, 1.11).
 *
 * בחודש עתידי מופיעים המופעים הצפויים, ולחיצה על אחד מהם מציעה "דלג על
 * החודש הזה". המופע עוד לא קיים כשורה — אין מה למחוק — אז רושמים את התאריך
 * ב-‎recurring_skips‎ של התבנית, ובדיוק כמו במחיקת מופע המנוע לא ייצר אותו.
 * ‎p_skip = false‎ מוריד את הדילוג ("בטל" בהודעה).
 *
 * עדכון אטומי אחד, ולא קריאה-שינוי-כתיבה מהאפליקציה: שני בני משפחה שדילגו
 * על שני חודשים באותה שנייה איבדו אחד (ראו ‎delete_recurring_occurrence‎).
 * רק תאריך עתידי — מה שכבר ירד הוא עסקה אמיתית, ונמחק כמו עסקה.
 */
create or replace function public.skip_recurring_date(
    p_template_id uuid,
    p_family_id   uuid,
    p_date        date,
    p_skip        boolean default true
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    v_updated integer;
begin
    if p_date <= (now() at time zone 'Asia/Jerusalem')::date then
        return 0;
    end if;

    -- ‎security definer‎ עוקף RLS — הגישה נגזרת מהמשתמש המחובר, במפורש
    update public.transactions
       set recurring_skips = case when p_skip then (
               select array_agg(distinct d order by d)
               from unnest(coalesce(recurring_skips, '{}'::date[]) || p_date) as d
           ) else array_remove(coalesce(recurring_skips, '{}'::date[]), p_date) end
     where id = p_template_id
       and is_recurring
       and family_id = p_family_id
       and family_id = (select family_id from public.profiles where id = auth.uid());
    get diagnostics v_updated = row_count;
    return v_updated;
end;
$$;

revoke all on function public.skip_recurring_date(uuid, uuid, date, boolean) from public, anon;
grant execute on function public.skip_recurring_date(uuid, uuid, date, boolean) to authenticated;
