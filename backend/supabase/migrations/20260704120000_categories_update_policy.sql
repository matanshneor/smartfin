-- Allow family members to edit (rename / change icon of) their custom categories
create policy categories_update on public.categories
  for update
  using (
    is_custom = true
    and family_id in (select family_id from public.profiles where id = auth.uid())
  )
  with check (
    is_custom = true
    and family_id in (select family_id from public.profiles where id = auth.uid())
  );
