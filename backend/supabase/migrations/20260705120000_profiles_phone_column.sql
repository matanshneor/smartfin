-- Optional phone number for the account settings page
alter table public.profiles add column if not exists phone text;
