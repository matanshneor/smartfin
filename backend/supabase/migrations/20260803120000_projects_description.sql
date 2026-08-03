-- Free-text description for a project, shown on the project overview page and
-- editable from the project edit screen. Nullable — existing projects keep no
-- description until one is written.
alter table public.projects add column if not exists description text;
