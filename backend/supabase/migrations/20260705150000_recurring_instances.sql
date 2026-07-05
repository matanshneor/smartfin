-- מנוע עסקאות קבועות: כל מופע חודשי/שבועי שנוצר אוטומטית מקושר לעסקת המקור.
-- מחיקת עסקת המקור משאירה את המופעים שכבר נוצרו (הכסף כבר זז) אך עוצרת יצירה עתידית.
alter table public.transactions
  add column if not exists recurring_parent_id uuid references public.transactions(id) on delete set null;

create index if not exists idx_tx_recurring_parent
  on public.transactions(recurring_parent_id) where recurring_parent_id is not null;
