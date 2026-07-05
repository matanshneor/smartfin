-- מכסת סריקות קבלה חודשית למשפחה (100 סריקות מוצלחות בחודש) —
-- כל שורה מייצגת סריקה מוצלחת אחת; סריקות שנכשלו (קבלה לא קריאה) לא נרשמות
-- וממילא אינן נספרות במכסה.
create table if not exists public.receipt_scans (
    id         uuid primary key default gen_random_uuid(),
    family_id  uuid not null references public.families(id) on delete cascade,
    user_id    uuid references public.profiles(id) on delete set null,
    created_at timestamptz not null default now()
);

alter table public.receipt_scans enable row level security;

create policy receipt_scans_family_select on public.receipt_scans
    for select using (
        family_id in (select profiles.family_id from public.profiles where profiles.id = auth.uid())
    );

create policy receipt_scans_family_insert on public.receipt_scans
    for insert with check (
        family_id in (select profiles.family_id from public.profiles where profiles.id = auth.uid())
    );

create index if not exists idx_receipt_scans_family_created
    on public.receipt_scans(family_id, created_at);
