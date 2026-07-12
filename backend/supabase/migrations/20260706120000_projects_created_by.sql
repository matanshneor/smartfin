-- מי יצר את הפרויקט במקור. חשוב במיוחד לפרויקט ששהיה אישי והפך למשותף —
-- ה-owner_id מתאפס אז ל-NULL, ורק created_by שומר מי רשאי להחזיר אותו
-- להיות אישי שוב.
alter table public.projects
    add column if not exists created_by uuid references public.profiles(id) on delete set null;

update public.projects set created_by = owner_id where owner_id is not null and created_by is null;
