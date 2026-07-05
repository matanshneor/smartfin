-- נתיב אחסון תמונת הקבלה המצורפת לעסקה (bucket פרטי "receipts").
alter table public.transactions
    add column if not exists receipt_path text;
