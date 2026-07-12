-- מחיקת חשבון עצמית + ארכיון פנימי לבעל האתר + תיעוד כניסות.
--
-- עקרונות:
-- 1. מבחינת המשתמש המחיקה סופית: החשבון וכל הנתונים נעלמים, והמייל/הטלפון
--    משתחררים להרשמה חדשה שלא "זוכרת" כלום.
-- 2. מבחינת בעל האתר כלום לא נעלם: חשבונות שנמחקו, משפחות שנמחקו וכל עסקה
--    שנמחקה (מכל מסלול) נשמרים ב-owner_archive.
-- 3. הטבלאות הפנימיות (owner_archive, login_events) עם RLS מופעל ובלי שום
--    policy — אף לקוח (anon/authenticated) לא יכול לקרוא או לכתוב אליהן.
--    הכתיבה נעשית רק דרך פונקציות/טריגרים SECURITY DEFINER, והקריאה רק
--    ישירות מ-Supabase (בעל האתר).

-- ── ארכיון פנימי ──────────────────────────────────────────────────────────
create table if not exists public.owner_archive (
    id          uuid primary key default gen_random_uuid(),
    kind        text not null,           -- 'transaction' | 'account' | 'family'
    payload     jsonb not null,
    archived_at timestamptz not null default now()
);
alter table public.owner_archive enable row level security;

-- ── תיעוד כניסות ──────────────────────────────────────────────────────────
create table if not exists public.login_events (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid,
    email      text,
    event      text not null default 'login',
    created_at timestamptz not null default now()
);
alter table public.login_events enable row level security;

create or replace function public.log_login_event(p_event text default 'login')
returns void
language plpgsql security definer set search_path = public as $$
begin
    insert into public.login_events (user_id, email, event)
    select u.id, u.email, p_event
    from auth.users u where u.id = auth.uid();
end;
$$;
grant execute on function public.log_login_event(text) to authenticated;

-- ── ארכוב כל מחיקת עסקה (מכל מסלול: ידנית, מחיקת פרויקט, מחיקת משפחה) ──────
create or replace function public.archive_deleted_transaction()
returns trigger
language plpgsql security definer set search_path = public as $$
begin
    insert into public.owner_archive (kind, payload) values ('transaction', to_jsonb(old));
    return old;
end;
$$;

drop trigger if exists trg_archive_deleted_transaction on public.transactions;
create trigger trg_archive_deleted_transaction
    before delete on public.transactions
    for each row execute function public.archive_deleted_transaction();

-- ── מחיקת חשבון עצמית ─────────────────────────────────────────────────────
-- אם נשארו חברי משפחה אחרים: רק החשבון נמחק, נתוני המשפחה נשארים, והשיוך
-- האישי של המשתמש הופך אוטומטית ל"משותפת" (FK ON DELETE SET NULL).
-- אם זה החבר האחרון: המשפחה כולה נמחקת (עסקאות מארוכבות דרך הטריגר).
create or replace function public.delete_my_account()
returns void
language plpgsql security definer set search_path = public as $$
declare
    v_uid    uuid := auth.uid();
    v_email  text;
    v_family uuid;
    v_others int  := 0;
begin
    if v_uid is null then
        raise exception 'not authenticated';
    end if;

    select email into v_email from auth.users where id = v_uid;
    select family_id into v_family from public.profiles where id = v_uid;

    if v_family is not null then
        select count(*) into v_others from public.profiles
        where family_id = v_family and id <> v_uid;
    end if;

    -- ארכוב החשבון (כולל מייל) לפני המחיקה
    insert into public.owner_archive (kind, payload)
    select 'account',
           to_jsonb(p) || jsonb_build_object(
               'email', v_email,
               'was_last_member', (v_family is not null and v_others = 0))
    from public.profiles p where p.id = v_uid;

    -- החבר האחרון — ארכוב המשפחה (עם הקטגוריות והפרויקטים שלה) ומחיקתה
    if v_family is not null and v_others = 0 then
        insert into public.owner_archive (kind, payload)
        select 'family', jsonb_build_object(
            'family',     to_jsonb(f),
            'categories', (select coalesce(jsonb_agg(to_jsonb(c)), '[]'::jsonb)
                           from public.categories c where c.family_id = f.id),
            'projects',   (select coalesce(jsonb_agg(to_jsonb(pr)), '[]'::jsonb)
                           from public.projects pr where pr.family_id = f.id))
        from public.families f where f.id = v_family;

        delete from public.families where id = v_family;
    end if;

    -- מחיקה מ-auth מוחקת בשרשור את הפרופיל ומשחררת מייל + טלפון להרשמה חדשה
    delete from auth.users where id = v_uid;
end;
$$;
grant execute on function public.delete_my_account() to authenticated;
