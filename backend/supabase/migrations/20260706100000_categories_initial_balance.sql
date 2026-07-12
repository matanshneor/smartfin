-- יתרה התחלתית לקופת חיסכון (רלוונטי רק כש-type='savings') — כדי שהעושר
-- המצטבר של קופה ישקף גם כסף שכבר היה קיים לפני שהתחלנו לעקוב באתר.
alter table public.categories
    add column if not exists initial_balance numeric(10, 2);
