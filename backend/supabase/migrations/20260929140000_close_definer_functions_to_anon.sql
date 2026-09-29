/* פונקציות SECURITY DEFINER שהיו פתוחות למי שלא מחובר, בלי צורך.
 *
 * יועץ האבטחה של Supabase סימן שש. אף אחת לא דלפה: כולן נגזרות מ-
 * ‎auth.uid()‎, שהוא ‎null‎ למי שלא מחובר, ולכן לא עשו כלום. אבל ברירת
 * המחדל של Postgres היא ‎execute‎ ל-PUBLIC, ואין סיבה שהדלת תהיה פתוחה.
 *
 * · ‎delete_my_account‎, ‎join_family_by_code‎, ‎log_login_event‎ — נקראות
 *   מהאפליקציה רק אחרי התחברות (‎log_login_event‎ אחרי ‎set_auth_token‎).
 *   נשארות ל-‎authenticated‎ בלבד.
 * · ‎handle_new_user‎, ‎archive_deleted_transaction‎ — פונקציות trigger.
 *   Postgres בודק ‎execute‎ עליהן רק ביצירת ה-trigger, לא בהפעלה, אז
 *   סגירה לכולם לא עוצרת אותן — רק את הקריאה הישירה דרך ‎/rest/v1/rpc‎.
 *
 * ‎get_my_family_id‎ נשארת פתוחה **בכוונה**: מדיניות ‎profiles_family_read‎
 * (לתפקיד PUBLIC) קוראת לה. סגירה שלה ל-anon הייתה הופכת "אין לך גישה"
 * (רשימה ריקה) לשגיאת הרשאה. היא מחזירה רק את המשפחה של הקורא, ו-‎null‎
 * למי שלא מחובר — אין בה מה לסגור.
 */
revoke all     on function public.delete_my_account()            from public, anon;
revoke all     on function public.join_family_by_code(text)      from public, anon;
revoke all     on function public.log_login_event(text)          from public, anon;
grant  execute on function public.delete_my_account()            to authenticated;
grant  execute on function public.join_family_by_code(text)      to authenticated;
grant  execute on function public.log_login_event(text)          to authenticated;

revoke all on function public.handle_new_user()              from public, anon, authenticated;
revoke all on function public.archive_deleted_transaction()  from public, anon, authenticated;

comment on function public.get_my_family_id() is
    'Open to anon on purpose: policy profiles_family_read (role PUBLIC) calls it; revoking would turn '
    'an empty result into a permission error. Returns null for anon. See 20260929140000.';
