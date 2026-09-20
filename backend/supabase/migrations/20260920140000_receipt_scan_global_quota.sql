/* תקרה גלובלית לסריקות קבלות.
 *
 * ‎/api/receipts/scan‎ הוא המסלול היחיד באפליקציה שעולה כסף אמיתי — הוא
 * קורא ל-OpenAI. המכסה הקיימת היא 100 סריקות **לכל משפחה**, וההרשמה
 * פתוחה: כל חשבון חדש מקבל משפחה, ואיתה מכסה טרייה. כלומר לא הייתה שום
 * תקרה על הסכום הכולל.
 *
 * הספירה חייבת לחצות משפחות, ו-RLS על receipt_scans מגבילה כל משתמש
 * למשפחה שלו — ולכן פונקציה, ולא שאילתה מהאפליקציה. היא מחזירה מספר
 * אחד בלבד: כמה סריקות בוצעו בסך הכול מאז תאריך. אין בה שום נתון של
 * אף משפחה.
 *
 * ‎p_since‎ מגיע מהאפליקציה ולא מחושב כאן, כדי שיהיה בדיוק אותו גבול
 * חודש כמו בספירה לכל משפחה — שם הוא נגזר משעון ישראל (backend/clock.py),
 * ו-‎now()‎ בשרת הוא UTC. בלי זה שתי הספירות היו מתאפסות בשעות שונות.
 */
create or replace function public.receipt_scans_global_since(p_since timestamptz)
returns integer
language sql
security definer
stable
set search_path = public
as $$
    select count(*)::int from public.receipt_scans where created_at >= p_since;
$$;

revoke all on function public.receipt_scans_global_since(timestamptz) from public, anon;
grant execute on function public.receipt_scans_global_since(timestamptz) to authenticated;

-- הספירה רצה לפני כל סריקה. עם 53 שורות זה לא משנה; עם 50,000 כן.
create index if not exists receipt_scans_created_at_idx on public.receipt_scans (created_at);
