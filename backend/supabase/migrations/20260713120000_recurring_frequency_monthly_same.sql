-- Allow a "same day-of-month" recurring frequency: recurs every month on the
-- transaction's own date (e.g. the 23rd), clamped to each month's last day for
-- 29/30/31. Widens the existing CHECK constraint alongside the fixed 1st/15th
-- and weekly/biweekly options.
alter table public.transactions
    drop constraint if exists transactions_recurring_frequency_check;

alter table public.transactions
    add constraint transactions_recurring_frequency_check
    check (recurring_frequency in ('monthly_same', 'monthly_1', 'monthly_15', 'weekly', 'biweekly'));
