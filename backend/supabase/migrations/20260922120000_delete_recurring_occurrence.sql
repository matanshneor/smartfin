/* מחיקת מופע בודד מסדרה קבועה — בלי להרוס את הסדרה.
 *
 * "רק את זו" על המופע הראשון מחק את שורת התבנית עצמה. ‎recurring_parent_id‎
 * הוא ‎on delete set null‎, אז כל שאר המופעים איבדו את הקישור בבת אחת:
 * הסדרה הפסיקה לייצר מופעים חדשים, וכל מה שכבר נוצר נעלם מ"עסקאות
 * קבועות" ומהפאנל בעמוד החודש. הממשק, באותו רגע, הודיע "שאר הסדרה
 * נשארה".
 *
 * ההבחנה בין "תבנית" ל"מופע" היא פנימית לגמרי. למי שמוחק את שכר הדירה
 * של מרץ לא אמור להיות אכפת שמרץ הוא במקרה החודש שבו הסדרה נפתחה —
 * ולכן מחיקת התבנית מעבירה את התפקיד למופע הבא במקום להרוג את הסדרה.
 *
 * הכול בפונקציה אחת ולא בשלוש קריאות מהאפליקציה, כי זו גם הנקודה שבה
 * ‎recurring_skips‎ היה read-modify-write: שני בני משפחה שמחקו שני
 * מופעים באותה שנייה איבדו דילוג אחד, והעסקה חזרה למחרת. כאן זה עדכון
 * אטומי אחד.
 */
create or replace function public.delete_recurring_occurrence(
    p_tx_id     uuid,
    p_family_id uuid
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    v_row       public.transactions%rowtype;
    v_template  uuid;
    v_heir      public.transactions%rowtype;
    v_deleted   integer;
begin
    -- הגישה נגזרת מהמשתמש המחובר, לא מהפרמטר: ‎security definer‎ עוקף
    -- RLS, אז הבדיקה חייבת להיות כאן ובמפורש.
    select * into v_row
    from public.transactions
    where id = p_tx_id
      and family_id = p_family_id
      and family_id = (select family_id from public.profiles where id = auth.uid());

    if not found then
        return 0;
    end if;

    v_template := case when v_row.is_recurring then v_row.id
                       else v_row.recurring_parent_id end;

    if v_template is null then
        delete from public.transactions where id = p_tx_id;
        return 1;
    end if;

    -- הדילוג נרשם על התבנית לפני כל מחיקה, כדי שהמנוע לא ייצר את
    -- התאריך הזה מחדש מחר.
    update public.transactions
       set recurring_skips = (
           select array_agg(distinct d)
           from unnest(coalesce(recurring_skips, '{}'::date[]) || v_row.date) as d
       )
     where id = v_template;

    -- מופע רגיל: מוחקים ומסיימים.
    if p_tx_id <> v_template then
        delete from public.transactions where id = p_tx_id;
        get diagnostics v_deleted = row_count;
        return v_deleted;
    end if;

    -- מכאן: מוחקים את **התבנית**. היורש הוא המופע המוקדם ביותר שנשאר.
    select * into v_heir
    from public.transactions
    where recurring_parent_id = v_template
      and family_id = p_family_id
    order by date, created_at
    limit 1;

    if found then
        -- היורש הופך לתבנית ונושא את כל מה שהגדיר את הסדרה.
        update public.transactions
           set is_recurring        = true,
               recurring_frequency = v_row.recurring_frequency,
               recurring_end_date  = v_row.recurring_end_date,
               recurring_skips     = (
                   select array_agg(distinct d)
                   from unnest(coalesce((select recurring_skips from public.transactions
                                          where id = v_template), '{}'::date[])) as d
               ),
               recurring_parent_id = null
         where id = v_heir.id;

        -- ושאר האחים מצביעים עליו. בלי זה הם היו מתייתמים ברגע
        -- שהתבנית הישנה נמחקת, וזה כל הבאג.
        update public.transactions
           set recurring_parent_id = v_heir.id
         where recurring_parent_id = v_template
           and id <> v_heir.id
           and family_id = p_family_id;
    end if;

    delete from public.transactions where id = v_template;
    get diagnostics v_deleted = row_count;
    return v_deleted;
end;
$$;

revoke all on function public.delete_recurring_occurrence(uuid, uuid) from public, anon;
grant execute on function public.delete_recurring_occurrence(uuid, uuid) to authenticated;
