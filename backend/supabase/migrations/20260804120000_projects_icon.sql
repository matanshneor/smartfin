-- Per-project emoji/icon, chosen and editable by the user (create + edit
-- screens). Nullable — when unset, the UI falls back to 🔒 (personal) / 🎯 (shared).
alter table public.projects add column if not exists icon text;
