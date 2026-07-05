-- Allow family members to rename their own family (the settings page's
-- "edit family name" feature and onboarding were silently failing without this).
create policy families_member_update on public.families
  for update
  using (
    id in (select family_id from public.profiles where id = auth.uid())
  )
  with check (
    id in (select family_id from public.profiles where id = auth.uid())
  );
