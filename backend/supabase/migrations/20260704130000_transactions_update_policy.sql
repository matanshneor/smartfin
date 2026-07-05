-- Allow family members to edit their own family's transactions
create policy transactions_family_update on public.transactions
  for update
  using (
    family_id in (select family_id from public.profiles where id = auth.uid())
  )
  with check (
    family_id in (select family_id from public.profiles where id = auth.uid())
  );
