/* הניקוי הלילי של קבלות יתומות — מוסר.
 *
 * ‎purge_orphan_receipts‎ (20260922170000) נכשלה בכל אחת משבע הריצות שלה:
 * Supabase חוסמת מחיקה ישירה מ-‎storage.objects‎ ("Direct deletion from
 * storage tables is not allowed. Use the Storage API instead"). היא לא
 * מחקה אף קובץ, ונכשלה כל לילה בלי שאיש ראה.
 *
 * מאז 29.9.2026 האפליקציה מוחקת בעצמה, דרך ממשק האחסון: סריקה שננטשה
 * (‎/api/receipts/discard‎), ומחיקות המוניות (פרויקט, הסרה, עזיבה). מה
 * שעוד יכול להתפספס — דפדפן שנסגר באמצע סריקה — הוא נדיר, ומתן בחר
 * (29.9.2026) לא לבנות לזה ניקוי עם מפתח service-role.
 *
 * שני הניקויים הלייליים האחרים (‎purge-login-events‎, ‎purge-owner-archive‎)
 * מוחקים מטבלאות רגילות ועובדים — 7 מתוך 7 — ונשארים.
 */
select cron.unschedule('purge-orphan-receipts')
 where exists (select 1 from cron.job where jobname = 'purge-orphan-receipts');

drop function if exists public.purge_orphan_receipts();
