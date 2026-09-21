/* ‎get_my_family_id()‎ והמדיניות שנשענת עליה — שוחזרו לקבצים ב-22.9.2026.
 *
 * שתיהן קיימות במסד מזמן ומעולם לא נכתבו כמיגרציה; הן נוצרו דרך לוח
 * הבקרה. התוצאה היא שבנייה של המסד מאפס מהקבצים האלה **לא מייצרת את
 * המסד הזה**, בשתי דרכים נפרדות:
 *
 * 1. ‎20260916110000‎ יוצרת שתי פונקציות ‎language sql‎ שקוראות ל-
 *    ‎get_my_family_id()‎. Postgres מוודא גוף של פונקציית SQL בזמן
 *    היצירה, אז המיגרציה הזאת פשוט נכשלת אם הפונקציה לא קיימת.
 *
 * 2. ‎profiles_family_read‎ נוצרה בקבצים בגרסה **רקורסיבית**: מדיניות
 *    SELECT על ‎profiles‎ ששואלת את ‎profiles‎ עצמה. בשרת היא מזמן
 *    מנוסחת דרך הפונקציה — שהיא ‎security definer‎ ולכן לא מפעילה את
 *    המדיניות שוב — אבל התיקון הזה נשאר רק שם.
 *
 * לכן התאריך: לפני ‎20260916110000‎, שהיא הצרכן הראשון.
 *
 * ההגדרה זהה בדיוק לזו שבשרת, כולל ההרשאות — אומת ב-rollback מול
 * ‎pg_get_functiondef‎ ו-‎proacl‎. זו מיגרציה של תיעוד, לא של שינוי.
 *
 * הערה: ההרשאה ניתנה גם ל-‎anon‎. לאנונימי ‎auth.uid()‎ הוא ‎NULL‎
 * והפונקציה מחזירה ‎NULL‎, אז אין דליפה — אבל ההרשאה מיותרת. לא
 * נוגעים בה כאן: ‎profiles_family_read‎ חלה על ‎public‎, וביטול
 * ההרשאה עלול להפיל קריאות שהמדיניות מתירה. שינוי כזה צריך בדיקה
 * משלו.
 */
create or replace function public.get_my_family_id()
returns uuid
language sql
stable
security definer
set search_path to 'public'
as $$
  SELECT family_id FROM profiles WHERE id = auth.uid();
$$;

grant execute on function public.get_my_family_id() to authenticated, anon, service_role;

-- הגרסה הלא-רקורסיבית, כפי שהיא בשרת
drop policy if exists "profiles_family_read" on public.profiles;
create policy "profiles_family_read" on public.profiles
    for select using (
        family_id is not null
        and family_id = public.get_my_family_id()
    );
