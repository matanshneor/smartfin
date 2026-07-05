-- מעדכן את יצירת הפרופיל האוטומטית כך שתקרא גם מספר טלפון מהרשמה,
-- לצד השם שכבר נקרא קודם.
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
    insert into public.profiles (id, name, phone)
    values (
        new.id,
        coalesce(new.raw_user_meta_data->>'name', 'משתמש'),
        new.raw_user_meta_data->>'phone'
    );
    return new;
end;
$$;
