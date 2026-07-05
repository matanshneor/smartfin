-- מונע יצירת מופע כפול של עסקה קבועה (למשל כששני בני משפחה
-- פותחים את האתר בו-זמנית וה-materializer רץ פעמיים במקביל).
create unique index if not exists uq_tx_recurring_occurrence
  on public.transactions(recurring_parent_id, date)
  where recurring_parent_id is not null;
