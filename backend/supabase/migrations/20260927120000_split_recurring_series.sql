/* "עדכן להבא" כתב מחדש את החודש הראשון של הסדרה.
 *
 * עורכים את שכר הדירה של ספטמבר ל-₪5,500 ועונים "כן" לשאלה "לעדכן גם
 * את התבנית כדי שהחודשים הבאים ישתמשו בסכום החדש?". האפליקציה עדכנה את
 * שורת התבנית — אבל התבנית **היא** שכר הדירה של ינואר, והיא נספרת
 * בסיכום של ינואר. ינואר הפך ל-₪5,500 בשקט, יחד עם התיאור והקטגוריה.
 * ה-docstring הבטיח "היסטוריה לא נכתבת מחדש".
 *
 * הפתרון הוא לא לגעת בתבנית אלא לפצל את הסדרה במופע שנערך:
 *   · הסדרה הישנה מסתיימת יום לפניו — בדיוק מה ש"את זו והבאות" עושה
 *     (‎delete_occurrences_from‎), כך שההיסטוריה נשארת סדרה מזוהה.
 *   · המופע שנערך — שכבר נושא את הסכום החדש, כי מסלול העריכה שמר אותו
 *     רגע קודם — הופך לתבנית של סדרה חדשה. אותו "יורש הופך לתבנית"
 *     כמו ב-‎delete_recurring_occurrence‎.
 *   · מופעים מאוחרים ממנו שכבר נוצרו עוברים לסדרה החדשה בלי שהסכום שלהם
 *     ישתנה: הם היסטוריה. בלי המעבר, הסדרה החדשה לא הייתה רואה אותם
 *     והייתה יוצרת אותם שוב — כפילות.
 *   · דילוגים (‎recurring_skips‎) מתחלקים לפי התאריך.
 *
 * הכול בפונקציה אחת: ארבע כתיבות מהאפליקציה היו משאירות, בכשל באמצע,
 * שתי סדרות חיות שמייצרות את אותו כסף.
 *
 * מחזירה את מזהה התבנית החדשה, או ‎null‎ כשאין מה לפצל — המופע לא
 * קיים, לא שייך לתבנית הזאת, לא של המשפחה של הקורא, או שהסדרה כבר
 * הסתיימה לפניו.
 */
create or replace function public.split_recurring_series(
    p_template_id uuid,
    p_instance_id uuid,
    p_family_id   uuid
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    v_template public.transactions%rowtype;
    v_instance public.transactions%rowtype;
begin
    -- ‎security definer‎ עוקף RLS, אז הבעלות נבדקת כאן ובמפורש, מול
    -- המשתמש המחובר ולא מול הפרמטר.
    if p_family_id is distinct from public.get_my_family_id() then
        return null;
    end if;

    select * into v_template
    from public.transactions
    where id = p_template_id
      and family_id = p_family_id
      and is_recurring
    for update;
    if not found then
        return null;
    end if;

    select * into v_instance
    from public.transactions
    where id = p_instance_id
      and family_id = p_family_id
      and recurring_parent_id = p_template_id
      and not is_recurring
    for update;
    if not found then
        return null;
    end if;

    -- מופע נוצר תמיד **אחרי** התבנית; מופע לפני הסיום בלבד. כל דבר אחר
    -- הוא נתון שבור, ופיצול שלו היה מפר את ה-CHECK על תאריך הסיום.
    if v_instance.date <= v_template.date
       or (v_template.recurring_end_date is not null
           and v_instance.date > v_template.recurring_end_date) then
        return null;
    end if;

    -- 1. המופע הופך לתבנית ולוקח ממנה את הגדרת הסדרה, ואת הדילוגים
    --    שמתאריכו והלאה.
    update public.transactions
       set is_recurring        = true,
           recurring_parent_id = null,
           recurring_frequency = v_template.recurring_frequency,
           recurring_end_date  = v_template.recurring_end_date,
           recurring_skips     = (
               select array_agg(d order by d)
               from unnest(coalesce(v_template.recurring_skips, '{}'::date[])) as d
               where d >= v_instance.date
           )
     where id = v_instance.id;

    -- 2. המופעים המאוחרים עוברים אליו.
    update public.transactions
       set recurring_parent_id = v_instance.id
     where recurring_parent_id = v_template.id
       and family_id = p_family_id
       and date > v_instance.date;

    -- 3. הסדרה הישנה נגמרת יום לפני, ושומרת רק את הדילוגים שלה.
    update public.transactions
       set recurring_end_date = v_instance.date - 1,
           recurring_skips    = (
               select array_agg(d order by d)
               from unnest(coalesce(v_template.recurring_skips, '{}'::date[])) as d
               where d < v_instance.date
           )
     where id = v_template.id;

    return v_instance.id;
end;
$$;

revoke all     on function public.split_recurring_series(uuid, uuid, uuid) from public, anon;
grant  execute on function public.split_recurring_series(uuid, uuid, uuid) to authenticated;
