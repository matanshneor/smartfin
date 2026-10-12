-- נשארים מחוברים גם כשתשובה הולכת לאיבוד (מתן, 13.10: "לפעמים דורש
-- להתחבר ולפעמים לא").
--
-- ה-refresh token של Supabase מתחלף בכל רענון, והישן נפסל. עד היום הטוקן
-- החדש נשמר רק בעוגייה — כלומר רק אם התשובה הגיעה לטלפון. באייפון זה לא
-- תמיד קורה: האפליקציה יורדת לרקע באמצע בקשה (‎499‎ ביומני Railway), השרת
-- כבר החליף את הטוקן, והעוגייה נשארת עם הישן. בכניסה הבאה: "Invalid Refresh
-- Token: Already Used" — וניתוק. 11 פעמים ביומיים (11–12.10).
--
-- התיקון: עותק של הטוקנים העדכניים בטבלה, לפי מזהה סשן אקראי שנמצא בעוגייה
-- (‎sid‎, 256 ביט). בקשה עם עוגייה ישנה מוצאת כאן את הטוקן שהחליף את שלה.
--
-- אבטחה: השרת שולח רק ‎sha256‎ של המזהה — המזהה עצמו לא נשמר במסד. מי שיש
-- לו את המזהה כבר מחזיק את העוגייה, שנושאת היום את ה-refresh token עצמו —
-- אז אין כאן גישה שלא הייתה קודם. אין גישה ישירה לטבלה (RLS בלי מדיניות);
-- רק דרך הפונקציות, וכל אחת דורשת את ה-hash.
create table if not exists public.web_sessions (
    sid_hash      text primary key,
    user_id       uuid not null references auth.users (id) on delete cascade,
    access_token  text not null,
    refresh_token text not null,
    expires_at    bigint not null,
    updated_at    timestamptz not null default now()
);
alter table public.web_sessions enable row level security;
create index if not exists web_sessions_user_id_idx on public.web_sessions (user_id);

-- בהתחברות: שורה חדשה בלבד, אף פעם לא דריסה של קיימת
create or replace function public.web_session_open(
    p_sid_hash text, p_user_id uuid, p_access text, p_refresh text, p_expires bigint)
returns void
language sql
security definer
set search_path = ''
as $$
    delete from public.web_sessions where updated_at < now() - interval '120 days';
    insert into public.web_sessions (sid_hash, user_id, access_token, refresh_token, expires_at)
    values (p_sid_hash, p_user_id, p_access, p_refresh, p_expires)
    on conflict (sid_hash) do nothing;
$$;

create or replace function public.web_session_get(p_sid_hash text)
returns table (access_token text, refresh_token text, expires_at bigint)
language sql
security definer
set search_path = ''
as $$
    select s.access_token, s.refresh_token, s.expires_at
    from public.web_sessions s where s.sid_hash = p_sid_hash;
$$;

-- אחרי רענון: רק אם הטוקן במסד הוא זה שרוענן (שני workers לא דורסים זה את זה)
create or replace function public.web_session_rotate(
    p_sid_hash text, p_old_refresh text, p_access text, p_refresh text, p_expires bigint)
returns boolean
language sql
security definer
set search_path = ''
as $$
    with u as (
        update public.web_sessions
        set access_token = p_access, refresh_token = p_refresh,
            expires_at = p_expires, updated_at = now()
        where sid_hash = p_sid_hash and refresh_token = p_old_refresh
        returning 1)
    select exists (select 1 from u);
$$;

create or replace function public.web_session_close(p_sid_hash text)
returns void
language sql
security definer
set search_path = ''
as $$
    delete from public.web_sessions where sid_hash = p_sid_hash;
$$;

revoke all on function public.web_session_open(text, uuid, text, text, bigint) from public;
revoke all on function public.web_session_get(text) from public;
revoke all on function public.web_session_rotate(text, text, text, text, bigint) from public;
revoke all on function public.web_session_close(text) from public;
grant execute on function public.web_session_open(text, uuid, text, text, bigint) to anon, authenticated;
grant execute on function public.web_session_get(text) to anon, authenticated;
grant execute on function public.web_session_rotate(text, text, text, text, bigint) to anon, authenticated;
grant execute on function public.web_session_close(text) to anon, authenticated;
