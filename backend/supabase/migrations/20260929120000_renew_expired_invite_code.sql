/* כל בן משפחה רואה בהגדרות קוד הזמנה תקף (בקשת מתן, 29.9.2026).
 *
 * ‎rotate_invite_code‎ היא של המנהל בלבד, ובצדק: היא מחליפה גם קוד שעוד
 * בתוקף — כלומר מבטלת הזמנות שכבר נשלחו. אבל חידוש של קוד **שכבר פג** לא
 * מבטל כלום, ואין סיבה שבן משפחה שנכנס להגדרות יראה "הקוד פג" ויחכה למנהל.
 *
 * לכן פונקציה נפרדת, שכל חבר רשאי להפעיל ושיודעת לעשות רק את זה: אם הקוד
 * חסר או פג — קוד חדש לשבוע; אחרת — כלום. אי אפשר להשתמש בה כדי לבטל קוד
 * תקף, אז ההרשאה של המנהל לא נחלשת.
 *
 * עדכון אחד עם התנאי בתוכו, ולא "בדוק ואז עדכן": שני בני משפחה שנכנסים
 * להגדרות באותה שנייה היו מפיקים שני קודים, ואחד מהם היה רואה קוד שכבר
 * הוחלף. כך השני לא מוצא מה לעדכן ומקבל את הקוד שהראשון הפיק.
 *
 * מחזירה את הקוד שבתוקף עכשיו — חדש או קיים.
 */
create or replace function public.renew_expired_invite_code()
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

    update public.families
       set invite_code            = public.gen_invite_code(),
           invite_code_expires_at = now() + interval '7 days'
     where id = v_family
       and (invite_code is null or invite_code_expires_at <= now());

    select invite_code into v_code from public.families where id = v_family;
    return v_code;
end;
$$;

revoke all     on function public.renew_expired_invite_code() from public, anon;
grant  execute on function public.renew_expired_invite_code() to authenticated;
