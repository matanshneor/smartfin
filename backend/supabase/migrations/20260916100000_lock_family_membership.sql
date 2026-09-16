/* שיוך משפחה נקבע רק דרך פונקציות, לא בכתיבה ישירה.
 *
 * הרקע: profiles_own הוגדרה FOR ALL USING (auth.uid() = id) בלי WITH CHECK.
 * ב-UPDATE, Postgres משתמש ב-USING גם כבדיקה על השורה החדשה — כלומר התנאי
 * היחיד על השורה שנכתבת הוא שהיא שלי. family_id לא הוגבל בכלל.
 *
 * הוכחתי את זה מול הנתונים האמיתיים (בתוך טרנזקציה שבוטלה): משתמש מאומת
 * מריץ UPDATE אחד על השורה שלו, מצביע על מזהה משפחה אחרת, ומאותו רגע כל
 * המדיניות בשאר הטבלאות נותנות לו גישה מלאה — כי כולן נגזרות מאותה עמודה.
 * families_insert היה WITH CHECK (true), כך שאפשר גם ליצור משפחות שרירותיות.
 *
 * זה לא היה ניתן לניצול דרך האפליקציה: אין מסלול Flask שמקבל family_id
 * מהמשתמש, וגישה ישירה ל-PostgREST דורשת את מפתח ה-anon ששמור בשרת בלבד.
 * אבל RLS אמורה להיות השכבה שתופסת באג עתידי בקוד, ולא עותק של אותה בדיקה.
 *
 * הפתרון עוקב אחרי הדפוס שכבר קיים כאן: join_family_by_code הוא SECURITY
 * DEFINER שנגזר מ-auth.uid(). עכשיו גם יצירת משפחה עובדת כך, וכתיבה ישירה
 * לעמודה נחסמת ברמת ההרשאות — לא ברמת מדיניות, כי WITH CHECK לא יכולה
 * להשוות לערך הקודם של השורה.
 */

-- ─── יצירת משפחה ושיוך, בפעולה אחת מבוקרת ──────────────────────────────────
create or replace function public.create_own_family(p_name text default 'המשפחה שלי')
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    v_uid      uuid := auth.uid();
    v_existing uuid;
    v_id       uuid;
begin
    if v_uid is null then
        raise exception 'not authenticated';
    end if;

    -- למי שכבר יש משפחה לא נוצרת חדשה ולא מוחלפת הקיימת. זה מה שמונע
    -- שימוש בפונקציה כדי לעבור בין משפחות.
    select family_id into v_existing from public.profiles where id = v_uid;
    if v_existing is not null then
        return v_existing;
    end if;

    v_id := gen_random_uuid();
    insert into public.families (id, name)
        values (v_id, coalesce(nullif(btrim(p_name), ''), 'המשפחה שלי'));
    update public.profiles set family_id = v_id where id = v_uid;
    return v_id;
end;
$$;

revoke all     on function public.create_own_family(text) from public, anon;
grant  execute on function public.create_own_family(text) to authenticated;

-- ─── אין יותר יצירת משפחות ישירה ───────────────────────────────────────────
drop policy if exists "families_insert" on public.families;
revoke insert on public.families from authenticated, anon;

-- ─── אין יותר שינוי שיוך ישיר ──────────────────────────────────────────────
-- הרשאת UPDATE ברמת הטבלה מכסה את כל העמודות, ולכן מסירים אותה ומחזירים
-- רק את העמודות שהמשתמש באמת עורך בהגדרות הפרופיל.
revoke update on public.profiles from authenticated, anon;
grant  update (name, avatar_initial, phone, workplace) on public.profiles to authenticated;

-- ─── הידוק המדיניות עצמה, להגנה בעומק ──────────────────────────────────────
alter policy "profiles_own" on public.profiles with check (auth.uid() = id);
