-- Allow any authenticated user to create a new family (needed for self-serve
-- signup without an invite code — ensure_family() was silently failing under RLS).
create policy families_insert on public.families
  for insert
  to authenticated
  with check (true);
