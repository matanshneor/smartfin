-- מאפשר התחברות גם עם מספר טלפון (לצד מייל): אינדקס ייחודי על טלפון
-- (מוחל רק כשהוא לא NULL — חשבונות ישנים בלי טלפון לא מושפעים), ופונקציית
-- lookup שמאפשרת ל-anon (לפני התחברות) למצוא את המייל המשויך לטלפון נתון.
-- הטלפון נשמר מנורמל (ספרות בלבד) ע"י ה-backend לפני הכתיבה, כך שההשוואה כאן
-- פשוטה ואמינה.
create unique index if not exists profiles_phone_unique_idx
    on public.profiles (phone) where phone is not null;

create or replace function public.email_for_phone(p_phone text)
returns text
language sql
security definer
set search_path = public
stable
as $$
    select u.email
    from public.profiles p
    join auth.users u on u.id = p.id
    where p.phone = p_phone
    limit 1;
$$;

grant execute on function public.email_for_phone(text) to anon, authenticated;
