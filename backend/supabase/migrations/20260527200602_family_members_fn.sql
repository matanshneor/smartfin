-- Allow family members to read each other's profiles
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
