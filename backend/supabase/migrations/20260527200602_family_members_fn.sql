/* המדיניות כאן מוגדרות גם בקובץ הסכימה הראשון. ל-‎CREATE POLICY‎ אין
 * ‎IF NOT EXISTS‎, אז בנייה מאפס נעצרה כאן ב-42710 — הפנקס מלא, אז
 * בפרויקט המקושר זה לא נראה, אבל שחזור מאסון, סביבת בדיקות ו-‎db reset‎
 * כולם נכשלו. ‎drop policy if exists‎ לפני כל אחת הופך את הקובץ לניתן
 * להרצה חוזרת בלי לשנות את התוצאה. */

-- Allow family members to read each other's profiles
drop policy if exists "profiles_family_read" on profiles;
CREATE POLICY "profiles_family_read" ON profiles
    FOR SELECT USING (
        family_id IS NOT NULL
        AND family_id IN (
            SELECT family_id FROM profiles WHERE id = auth.uid()
        )
    );

-- Returns all profiles in the same family (bypasses RLS)
CREATE OR REPLACE FUNCTION get_family_members(p_family_id UUID)
RETURNS TABLE (
    id              UUID,
    name            TEXT,
    avatar_initial  TEXT
)
LANGUAGE SQL STABLE SECURITY DEFINER AS $$
    SELECT id, name, avatar_initial
    FROM profiles
    WHERE family_id = p_family_id
    ORDER BY created_at;
$$;
