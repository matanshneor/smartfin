/* גבולות דלי הקבלות, וניקוי הקבצים שאיש לא מצביע עליהם.
 *
 * **הגבולות כבר קיימים בשרת** — 8MB ורשימת סוגים — אבל הם הוגדרו דרך
 * לוח הבקרה ומעולם לא נכתבו כמיגרציה. כלומר בנייה מאפס מהריפו מייצרת
 * דלי פתוח לכל גודל ולכל סוג קובץ, שההגנה היחידה עליו היא בדיקה
 * ב-Flask. זו בדיוק אותה מחלקה של ‎get_my_family_id‎ ושל תשע המדיניות
 * הכפולות: הפנקס מלא, התוכן לא.
 *
 * 6MB ולא 8: זה מה ש-‎/api/receipts/scan‎ אוכף בפועל (app.py). שני
 * מספרים שונים לאותו גבול פירושם שאחד מהם לא נבדק אף פעם.
 *
 * **ויתומים.** ‎upload_receipt‎ מעלה **לפני** שנוצרה עסקה, והנתיב נמחק
 * רק ב-‎delete_transaction‎. כל מודאל סריקה שננטש משאיר קובץ שאף שורה
 * לא מצביעה עליו ושום קוד לא ימחק — על דלי של 1GB בתוכנית החינמית. כבר
 * עכשיו אחד משני הקבצים בדלי הוא יתום.
 */
update storage.buckets
   set file_size_limit   = 6 * 1024 * 1024,
       allowed_mime_types = array['image/jpeg', 'image/png', 'image/webp']
 where id = 'receipts';

create or replace function public.purge_orphan_receipts()
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    v_deleted integer;
begin
    -- חלון של 24 שעות לפני שקובץ נחשב יתום: סריקה שהועלתה זה עתה עדיין
    -- ממתינה שהמשתמש ילחץ "שמור", והעסקה שתצביע עליה עוד לא קיימת.
    delete from storage.objects o
     where o.bucket_id = 'receipts'
       and o.created_at < now() - interval '24 hours'
       and not exists (select 1 from public.transactions t
                        where t.receipt_path = o.name);
    get diagnostics v_deleted = row_count;
    return v_deleted;
end;
$$;

revoke all on function public.purge_orphan_receipts() from public, anon, authenticated;

select cron.unschedule('purge-orphan-receipts')
 where exists (select 1 from cron.job where jobname = 'purge-orphan-receipts');

select cron.schedule('purge-orphan-receipts', '57 3 * * *',
                     $cron$select public.purge_orphan_receipts()$cron$);
