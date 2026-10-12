-- עסקה בתשלומים (מתן, 12.10): "מקרר ₪4,800 ב-12 תשלומים".
--
-- תשלומים הם עסקה קבועה חודשית (‎monthly_same‎) עם תאריך סיום — המנוע הקיים
-- (‎materialize_recurring‎) יוצר תשלום בכל חודש. שלוש העמודות האלה רק אומרות
-- שזו סדרת תשלומים:
--   installments       — כמה תשלומים בסך הכול (על התבנית ועל כל מופע)
--   installment_no     — מספר התשלום הזה (התבנית — 1; מופע — לפי החודש)
--   installment_total  — הסכום המלא; ממנו מחושב התשלום הרגיל, והעיגול
--                        (אגורות שלא מתחלקות) נכנס לתשלום הראשון
alter table public.transactions
    add column if not exists installments smallint
        check (installments is null or installments between 2 and 60),
    add column if not exists installment_no smallint
        check (installment_no is null or installment_no >= 1),
    add column if not exists installment_total numeric(12, 2)
        check (installment_total is null or installment_total > 0);
