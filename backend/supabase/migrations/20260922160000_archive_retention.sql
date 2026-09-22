/* "מחיקת חשבון לצמיתות" לא מחקה כלום.
 *
 * ‎delete_my_account‎ מארכבת את הפרופיל (שם, אימייל, טלפון, מקום עבודה),
 * את המשפחה, הקטגוריות והפרויקטים; והטריגר ‎archive_deleted_transaction‎
 * מעתיק **כל** עסקה שנמחקת אי-פעם. הכול ל-‎owner_archive‎, בלי שום קוד
 * בכל הריפו שמנקה אותו. לנצח.
 *
 * מדיניות הפרטיות הבטיחה "מחיקת החשבון... מסירה את הפרופיל ואת הנתונים
 * הקשורים אליו" ו"הנתונים נשמרים כל עוד החשבון פעיל". שתי הטענות לא
 * היו נכונות. באפליקציה מאוחסנת באיחוד האירופי שמעבדת נתונים פיננסיים
 * זה כשל ישיר בסעיף 17 (זכות המחיקה) וב-5(1)(e) (הגבלת אחסון) — וגרוע
 * מזה, מפני שההבטחה נכתבה במפורש.
 *
 * ובמקביל זה גם מגבר: אין שום הגבלת קצב שמונעת "הוסף-מחק-חזור", וכל
 * מחזור כזה הוסיף שורה קבועה למסד של 500MB.
 *
 * 30 יום הוא החלון: מספיק כדי לעזור למי שמחק בטעות ופנה, וקצר מספיק
 * כדי שההבטחה במדיניות תהיה נכונה. המדיניות עודכנה לומר את זה במפורש.
 */
create or replace function public.purge_expired_archive()
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    v_deleted integer;
begin
    delete from public.owner_archive
     where archived_at < now() - interval '30 days';
    get diagnostics v_deleted = row_count;
    return v_deleted;
end;
$$;

revoke all on function public.purge_expired_archive() from public, anon, authenticated;

-- ‎login_events‎ באותו היגיון. המדיניות מצהירה על "רישום כניסות... לצורכי
-- אבטחה ואיתור שימוש לרעה", בלי לומר לכמה זמן — ובלי שום ניקוי. 90 יום
-- מספיקים לחקירה ולא הופכים את הטבלה לתיעוד תנועה קבוע של כל משתמש.
create or replace function public.purge_expired_login_events()
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    v_deleted integer;
begin
    delete from public.login_events
     where created_at < now() - interval '90 days';
    get diagnostics v_deleted = row_count;
    return v_deleted;
end;
$$;

revoke all on function public.purge_expired_login_events() from public, anon, authenticated;

create index if not exists owner_archive_archived_at_idx
    on public.owner_archive (archived_at);

/* התזמון. ‎pg_cron‎ ולא ניקוי מתוך האפליקציה: ניקוי שתלוי בכך שמישהו
 * ייכנס הוא בדיוק מה שמפסיק לעבוד כשאף אחד לא נכנס — והמקרה שבו הטבלה
 * הכי צריכה להתנקות הוא חשבון שנמחק ואיש לא חוזר אליו. */
create extension if not exists pg_cron;

select cron.unschedule('purge-owner-archive')
 where exists (select 1 from cron.job where jobname = 'purge-owner-archive');
select cron.unschedule('purge-login-events')
 where exists (select 1 from cron.job where jobname = 'purge-login-events');

select cron.schedule('purge-owner-archive', '17 3 * * *',
                     $cron$select public.purge_expired_archive()$cron$);
select cron.schedule('purge-login-events',  '37 3 * * *',
                     $cron$select public.purge_expired_login_events()$cron$);
