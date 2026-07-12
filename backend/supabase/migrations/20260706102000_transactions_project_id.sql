-- קישור אופציונלי בין עסקה לפרויקט. מחיקת פרויקט לא מוחקת את העסקאות שלו —
-- רק מנתקת אותן ממנו (הן חוזרות להיספר תחת הקטגוריה הרגילה שלהן).
alter table public.transactions
    add column if not exists project_id uuid references public.projects(id) on delete set null;
