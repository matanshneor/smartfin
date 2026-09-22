/* כל חבר במשפחה יכול היה למנות את עצמו למנהל.
 *
 * ‎families_member_update‎ היא ‎for update using (id in (...))‎ בלי שום
 * הגבלת עמודות, ובניגוד ל-‎profiles‎ (ראו 20260916100000) לא הייתה על
 * ‎families‎ שום ‎grant update (...)‎ מצומצמת. כלומר ברמת RLS
 * ‎UPDATE families SET manager_id = auth.uid()‎ מותר לכל חבר — וכך גם
 * ‎SET invite_code = 'AAAAAA'‎ ו-‎SET settings = '{}'‎.
 *
 * לא נגיש דרך Flask: ‎update_family_name‎ שולחת ‎name‎ בלבד, וההגדרות
 * עוברות דרך ‎merge_family_settings‎. אבל **כל** בדיקת ‎_require_manager‎
 * באפליקציה נשענת על עמודה שכל חבר יכול לכתוב, וזו בדיוק הטענה שהמיגרציה
 * על ‎profiles‎ עשתה בעצמה: "RLS אמורה לתפוס באג עתידי בקוד, לא להיות
 * עותק של אותה בדיקה".
 *
 * ‎invite_code‎ מוחרג גם הוא: החלפתו היא פעולת מנהל (‎rotate_invite_code‎,
 * שהיא ‎security definer‎ ובודקת בעצמה), וכתיבה ישירה אליו עוקפת את זה.
 */
revoke update on public.families from authenticated;
grant  update (name, settings) on public.families to authenticated;
