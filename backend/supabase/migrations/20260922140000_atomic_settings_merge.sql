/* הגדרות המשפחה נשמרו ב-read-modify-write, בלי נעילה.
 *
 * ‎update_family_settings‎ שלפה את ה-JSON, מיזגה בפייתון, וכתבה בחזרה את
 * המפה המלאה. ארבעה gunicorn workers, שורה אחת, ובלי שום ‎where settings
 * = <old>‎:
 *
 *   20:00:00.1  אמא קובעת תקציב ₪2,000 ל"סופר ומזון"
 *   20:00:00.3  אבא מכבה "שיוך הוצאות" מהטלפון
 *
 * שניהם קראו את אותו JSON. הכתיבה של אבא נושאת את ‎limits‎ מלפני אמא
 * ומוחקת את התקציב שלה. שניהם קיבלו ‎{"status":"ok"}‎, והמסך של אמא
 * המשיך להציג את התקציב עד הרענון הבא. ‎limits‎ הוא מפתח-החלפה, אז
 * האובדן מלא ולא חלקי — וב-‎owner_attribution‎ מדובר בשאלה של **לאן
 * משויך כסף**.
 *
 * המיזוג עובר לכאן, לתוך משפט ‎UPDATE‎ אחד. הסמנטיקה זהה ל-
 * ‎_merge_settings‎: עומק אחד, עם רשימת מפתחות שמוחלפים במלואם.
 */
create or replace function public.merge_family_settings(
    p_family_id  uuid,
    p_patch      jsonb,
    p_whole_keys text[] default array['limits']
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_settings jsonb;
    v_key      text;
    v_new      jsonb;
    v_old      jsonb;
begin
    if p_family_id is null then
        raise exception 'no family';
    end if;

    -- הגישה נגזרת מהמשתמש המחובר: ‎security definer‎ עוקף RLS.
    if not exists (select 1 from public.profiles
                    where id = auth.uid() and family_id = p_family_id) then
        raise exception 'not a member of that family';
    end if;

    -- ‎for update‎ נועל את השורה עד סוף המשפט, כך שהקורא השני ממתין
    -- וממזג על הערך **אחרי** הראשון במקום על הערך שלפניו.
    select coalesce(settings, '{}'::jsonb) into v_settings
      from public.families where id = p_family_id for update;

    for v_key in select jsonb_object_keys(coalesce(p_patch, '{}'::jsonb))
    loop
        v_new := p_patch -> v_key;
        v_old := v_settings -> v_key;

        if v_key = any(p_whole_keys) then
            -- מפה שלמה: הסרת תקציב מיוצגת בהיעדרו מהמפה, אז מיזוג לא
            -- יכול לבטא אותה — רק החלפה.
            v_settings := jsonb_set(v_settings, array[v_key], v_new, true);
        elsif jsonb_typeof(v_new) = 'object' and jsonb_typeof(v_old) = 'object' then
            v_settings := jsonb_set(v_settings, array[v_key], v_old || v_new, true);
        else
            v_settings := jsonb_set(v_settings, array[v_key], v_new, true);
        end if;
    end loop;

    update public.families set settings = v_settings where id = p_family_id;
    return v_settings;
end;
$$;

revoke all on function public.merge_family_settings(uuid, jsonb, text[]) from public, anon;
grant execute on function public.merge_family_settings(uuid, jsonb, text[]) to authenticated;
