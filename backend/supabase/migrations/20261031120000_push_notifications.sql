/* התראות לטלפון — Web Push (מתן, 31.10).
 *
 * ‎push_subscriptions‎: מכשיר אחד לכל שורה. כל משתמש רואה ומנהל רק את שלו;
 * מי מקבל מה נקבע בשתי פונקציות security definer:
 *
 *   ‎push_family_targets‎ — ברגע של פעולה (בן משפחה הצטרף, משכורת נרשמה):
 *     רק חבר במשפחה יכול לקבל את מכשירי המשפחה שלו, ורק שלה.
 *   ‎push_daily‎ — פעם ביום, מ-‎pg_cron‎ דרך האפליקציה. אין שם משתמש מחובר,
 *     ולכן הפונקציה פתוחה ל-anon אבל דורשת סוד ששמור ב-Vault
 *     (‎push_cron_secret‎) — ובלעדיו לא מחזירה כלום. האפליקציה מקבלת את אותו
 *     סוד ממשתנה סביבה (‎PUSH_CRON_SECRET‎). כך לא נוסף לשרת מפתח שירות
 *     שעוקף את כל ה-RLS.
 *
 * ‎push_log‎: מה כבר נשלח (סוג, משפחה, תקופה) — כדי שאף התראה לא תישלח פעמיים,
 * גם אם המשימה רצה פעמיים או ששני בני משפחה רשמו משכורת באותו חודש.
 *
 * הסודות עצמם לא בקובץ הזה (הריפו ציבורי). הם נוצרים פעם אחת ידנית:
 *   select vault.create_secret('<סוד>', 'push_cron_secret');
 *   select vault.create_secret('https://<האתר>/internal/push/daily', 'push_cron_url');
 */

-- ─── מנויים ──────────────────────────────────────────────────────────────────

create table if not exists public.push_subscriptions (
    endpoint    text primary key check (endpoint like 'https://%' and length(endpoint) <= 1000),
    user_id     uuid not null default auth.uid() references public.profiles(id) on delete cascade,
    p256dh      text not null check (length(p256dh) <= 200),
    auth        text not null check (length(auth) <= 100),
    created_at  timestamptz not null default now()
);
create index if not exists push_subscriptions_user_idx on public.push_subscriptions (user_id);

alter table public.push_subscriptions enable row level security;

drop policy if exists push_subscriptions_own on public.push_subscriptions;
create policy push_subscriptions_own on public.push_subscriptions
    for all to authenticated
    using (user_id = (select auth.uid()))
    with check (user_id = (select auth.uid()));

/* הרשמת המכשיר הזה למשתמש המחובר. security definer כי אותו טלפון יכול לעבור
 * בין שני בני משפחה (התנתקות והתחברות) — ואז השורה כבר רשומה על השני, ו-RLS
 * לא היה מאפשר לעדכן אותה. מי שמחזיק ב-endpoint הוא הדפדפן עצמו, אז
 * העברתו למחובר הנוכחי לא נותנת לאף אחד משהו שלא היה לו. */
create or replace function public.push_subscribe(p_endpoint text, p_p256dh text, p_auth text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    if auth.uid() is null then
        raise exception 'not signed in';
    end if;
    insert into public.push_subscriptions (endpoint, user_id, p256dh, auth)
    values (p_endpoint, auth.uid(), p_p256dh, p_auth)
    on conflict (endpoint) do update
        set user_id = excluded.user_id, p256dh = excluded.p256dh, auth = excluded.auth,
            created_at = now();
end;
$$;

revoke all on function public.push_subscribe(text, text, text) from public, anon;
grant execute on function public.push_subscribe(text, text, text) to authenticated;

-- ─── מה נשלח ─────────────────────────────────────────────────────────────────

create table if not exists public.push_log (
    kind       text not null,
    family_id  uuid not null references public.families(id) on delete cascade,
    period     text not null,
    sent_at    timestamptz not null default now(),
    primary key (kind, family_id, period)
);
-- בלי מדיניות בכלל: רק הפונקציות למטה נוגעות בה
alter table public.push_log enable row level security;

-- ─── ברגע של פעולה ───────────────────────────────────────────────────────────

/* מכשירי המשפחה, חוץ ממי שעשה את הפעולה. ‎p_kind/p_period‎ — אם נשלחו, זו
 * התראה של פעם אחת לתקופה (משכורת: פעם בחודש), והפונקציה רושמת אותה; אם
 * כבר נרשמה — לא מחזירה אף מכשיר. */
create or replace function public.push_family_targets(p_kind text default null, p_period text default null)
returns table (endpoint text, p256dh text, auth text)
language plpgsql
security definer
set search_path = public
as $$
#variable_conflict use_column
declare
    v_family uuid := public.get_my_family_id();
    v_rows   int;
begin
    if v_family is null then
        return;
    end if;
    if p_kind is not null then
        insert into public.push_log (kind, family_id, period)
        values (p_kind, v_family, coalesce(p_period, ''))
        on conflict do nothing;
        get diagnostics v_rows = row_count;
        if v_rows = 0 then
            return;
        end if;
    end if;
    return query
        select s.endpoint, s.p256dh, s.auth
        from public.push_subscriptions s
        join public.profiles p on p.id = s.user_id
        where p.family_id = v_family and s.user_id <> auth.uid();
end;
$$;

revoke all on function public.push_family_targets(text, text) from public, anon;
grant execute on function public.push_family_targets(text, text) to authenticated;

-- ─── פעם ביום ────────────────────────────────────────────────────────────────

create or replace function public._push_secret_ok(p_secret text)
returns boolean
language sql
security definer
stable
set search_path = public
as $$
    select coalesce(p_secret, '') <> '' and exists (
        select 1 from vault.decrypted_secrets
        where name = 'push_cron_secret' and decrypted_secret = p_secret
    );
$$;
revoke all on function public._push_secret_ok(text) from public, anon, authenticated;

/* כל מה שצריך לשלוח היום: שורה לכל (התראה, מכשיר). ‎data‎ — המספרים לנוסח;
 * הנוסח עצמו בעברית נבנה באפליקציה (‎backend/push.py‎). כל התראה נרשמת
 * ב-‎push_log‎ כאן, כך שריצה שנייה באותו יום לא מחזירה אותה שוב.
 *
 * ‎p_today‎ מגיע מהאפליקציה (שעון ישראל, ‎backend/clock.py‎) — השרת כאן ב-UTC. */
create or replace function public.push_daily(p_secret text, p_today date)
returns table (kind text, data jsonb, endpoint text, p256dh text, auth text)
language plpgsql
security definer
set search_path = public
as $$
#variable_conflict use_column
declare
    v_prev date := (date_trunc('month', p_today) - interval '1 month')::date;
begin
    if not public._push_secret_ok(p_secret) then
        return;
    end if;

    drop table if exists _due;
    create temporary table _due (kind text, family_id uuid, period text, data jsonb) on commit drop;

    -- חודש נסגר — ב-1 לחודש, לכל משפחה שהיו לה עסקאות (בלי פרויקטים)
    if extract(day from p_today) = 1 then
        insert into _due
        select 'month_closed', t.family_id, to_char(v_prev, 'YYYY-MM'),
               jsonb_build_object(
                   'month',   extract(month from v_prev)::int,
                   'income',  coalesce(sum(t.amount) filter (where t.type = 'income'), 0),
                   'expense', coalesce(sum(t.amount) filter (where t.type = 'expense'), 0),
                   'savings', coalesce(sum(t.amount) filter (where t.type = 'savings'), 0))
        from public.transactions t
        where t.project_id is null
          and t.date >= v_prev and t.date < date_trunc('month', p_today)::date
        group by t.family_id;
    end if;

    -- תשלום אחרון — סדרת תשלומים שמסתיימת היום (התבנית נושאת את הסדרה)
    insert into _due
    select 'last_installment', t.family_id, t.id::text,
           jsonb_build_object('description', coalesce(t.description, ''),
                              'amount', floor(t.installment_total * 100 / t.installments) / 100)
    from public.transactions t
    where t.installments is not null and t.is_recurring
      and t.recurring_end_date = p_today and t.project_id is null;

    -- שבוע בלי עסקה חדשה — אחרי 7, 14 ו-21 יום, ואז שקט
    insert into _due
    select 'quiet_week', q.family_id, 'w' || q.weeks || '-' || to_char(q.last_at, 'YYYY-MM-DD'),
           jsonb_build_object('weeks', q.weeks)
    from (
        select t.family_id, max(t.created_at) as last_at,
               floor(extract(epoch from (now() - max(t.created_at))) / 604800)::int as weeks
        from public.transactions t
        group by t.family_id
    ) q
    where q.weeks between 1 and 3;

    -- רק מה שעוד לא נשלח — ורושמים אותו באותה פקודה
    return query
        with fresh as (
            insert into public.push_log (kind, family_id, period)
            select d.kind, d.family_id, d.period from _due d
            on conflict do nothing
            returning push_log.kind, push_log.family_id, push_log.period
        )
        select d.kind, d.data, s.endpoint, s.p256dh, s.auth
        from fresh f
        join _due d on d.kind = f.kind and d.family_id = f.family_id and d.period = f.period
        join public.profiles p on p.family_id = d.family_id
        join public.push_subscriptions s on s.user_id = p.id;
end;
$$;

revoke all on function public.push_daily(text, date) from public;
grant execute on function public.push_daily(text, date) to anon, authenticated;

/* מכשיר שהשירות אמר עליו "כבר לא קיים" (404/410) — נמחק. גם כאן הסוד. */
create or replace function public.push_forget(p_secret text, p_endpoints text[])
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    if public._push_secret_ok(p_secret) then
        delete from public.push_subscriptions where endpoint = any(p_endpoints);
    end if;
end;
$$;

revoke all on function public.push_forget(text, text[]) from public;
grant execute on function public.push_forget(text, text[]) to anon, authenticated;

-- ─── התזמון ──────────────────────────────────────────────────────────────────

create extension if not exists pg_net with schema extensions;

/* כל יום ב-07:05 UTC — 09:05 בחורף ו-10:05 בקיץ בישראל. pg_cron קורא
 * לאפליקציה, והיא שולחת. בלי שני הסודות ב-Vault הקריאה פשוט לא יוצאת. */
select cron.schedule('push-daily', '5 7 * * *', $cron$
    select net.http_post(
        url     := (select decrypted_secret from vault.decrypted_secrets where name = 'push_cron_url'),
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'X-Cron-Secret', (select decrypted_secret from vault.decrypted_secrets where name = 'push_cron_secret')),
        body    := '{}'::jsonb)
    where exists (select 1 from vault.decrypted_secrets where name = 'push_cron_url');
$cron$);
