/* תיקון מיידי ל-20260928130000: המפתח הזר של ‎created_by‎ ל-‎profiles‎ הוסיף
 * קשר שני בין ‎transactions‎ ל-‎profiles‎ (בנוסף ל-‎user_id‎). PostgREST לא
 * יודע איזה מהם מתכוונים ב-‎profiles(name, workplace)‎, ומחזיר PGRST201 —
 * וכל שליפת עסקאות באפליקציה משתמשת בזה. דף הבית, עמוד החודש והפרויקטים
 * נפלו בייצור לכמה דקות, מרגע ההחלה.
 *
 * העמודה נשארת, בלי המפתח הזר. היא לא צריכה אותו: השם נגזר מרשימת בני
 * המשפחה, ומי שכבר לא בה מוצג "בן משפחה לשעבר". הלקח — כל מפתח זר נוסף
 * ל-‎profiles‎ מ-‎transactions‎ שובר את ה-embed הקיים.
 */
alter table public.transactions drop constraint if exists transactions_created_by_fkey;
