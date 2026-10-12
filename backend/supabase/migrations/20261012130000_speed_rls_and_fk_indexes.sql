-- מהירות (מתן, 12.10) — מה ש-Performance Advisor של Supabase מצא.
--
-- 1. מדיניות RLS שקוראות ל-‎auth.uid()‎ בתוך תנאי השורה: Postgres מחשב אותה
--    מחדש לכל שורה. ‎(select auth.uid())‎ מחושב פעם אחת לשאילתה. התנאי עצמו
--    לא משתנה — ‎alter policy‎ שומר על השם, הפעולה והתפקידים. 21 מדיניות.
-- 2. 13 מפתחות זרים בלי אינדקס — בהם ‎transactions.category_id / project_id /
--    user_id‎, שכל עמוד מסנן או מצרף לפיהם.

alter policy categories_delete on public.categories
    using ((is_custom = true) AND (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid())))));

alter policy categories_insert on public.categories
    with check (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))));

alter policy categories_read on public.categories
    using ((family_id IS NULL) OR (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid())))));

alter policy categories_update on public.categories
    using ((is_custom = true) AND (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid())))))
    with check ((is_custom = true) AND (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid())))));

alter policy families_member_read on public.families
    using (id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))));

alter policy families_member_update on public.families
    using (id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))))
    with check (id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))));

alter policy profiles_own on public.profiles
    using ((select auth.uid()) = id)
    with check ((select auth.uid()) = id);

alter policy project_categories_family_delete on public.project_categories
    using (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))));

alter policy project_categories_family_insert on public.project_categories
    with check (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))));

alter policy project_categories_family_select on public.project_categories
    using (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))));

alter policy project_categories_family_update on public.project_categories
    using (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))))
    with check (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))));

alter policy projects_family_delete on public.projects
    using (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))));

alter policy projects_family_insert on public.projects
    with check (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))));

alter policy projects_family_select on public.projects
    using (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))));

alter policy projects_family_update on public.projects
    using (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))))
    with check (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))));

alter policy receipt_scans_family_insert on public.receipt_scans
    with check (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))));

alter policy receipt_scans_family_select on public.receipt_scans
    using (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))));

alter policy transactions_family_delete on public.transactions
    using (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))));

alter policy transactions_family_insert on public.transactions
    with check (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))));

alter policy transactions_family_select on public.transactions
    using (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))));

alter policy transactions_family_update on public.transactions
    using (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))))
    with check (family_id IN ( SELECT profiles.family_id FROM profiles WHERE (profiles.id = (select auth.uid()))));

create index if not exists categories_family_id_idx on public.categories (family_id);
create index if not exists families_manager_id_idx on public.families (manager_id);
create index if not exists profiles_family_id_idx on public.profiles (family_id);
create index if not exists project_categories_family_id_idx on public.project_categories (family_id);
create index if not exists project_categories_project_id_idx on public.project_categories (project_id);
create index if not exists projects_created_by_idx on public.projects (created_by);
create index if not exists projects_family_id_idx on public.projects (family_id);
create index if not exists projects_owner_id_idx on public.projects (owner_id);
create index if not exists receipt_scans_user_id_idx on public.receipt_scans (user_id);
create index if not exists transactions_category_id_idx on public.transactions (category_id);
create index if not exists transactions_project_category_id_idx on public.transactions (project_category_id);
create index if not exists transactions_project_id_idx on public.transactions (project_id);
create index if not exists transactions_user_id_idx on public.transactions (user_id);
