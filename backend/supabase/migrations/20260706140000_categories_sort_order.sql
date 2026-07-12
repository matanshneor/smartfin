-- סדר תצוגה מותאם-אישית לקטגוריות (במקום סדר אלפביתי קבוע) — נקבע דרך
-- כפתורי ▲▼ בהגדרות, ומשפיע גם על רשת הקטגוריות במודאל הוספת/עריכת עסקה.
alter table public.categories add column if not exists sort_order integer;

-- מילוי התחלתי: סדר אלפביתי כמו היום, אבל "אחר" תמיד אחרונה בכל קבוצה
-- (family_id, type) — תואם למה שכבר מוצג במודאל, כדי שהמעבר לא "יקפוץ".
with ranked as (
    select id,
           row_number() over (
               partition by family_id, type
               order by (name = 'אחר')::int, name
           ) as rn
    from public.categories
)
update public.categories c set sort_order = ranked.rn
from ranked where ranked.id = c.id;
