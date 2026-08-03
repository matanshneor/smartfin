-- Project-linked transactions are excluded from the monthly balance everywhere
-- (they're large one-off/capital items that skew the "normal month" picture and
-- are shown separately). Keep the comparison page (get_months_archive) consistent
-- by excluding project transactions from its per-month totals too.
CREATE OR REPLACE FUNCTION get_months_archive(p_family_id UUID)
RETURNS TABLE (
    year     INT,
    month    INT,
    income   NUMERIC,
    expense  NUMERIC,
    savings  NUMERIC,
    balance  NUMERIC
)
LANGUAGE SQL STABLE SECURITY DEFINER AS $$
    SELECT
        EXTRACT(YEAR  FROM date)::INT  AS year,
        EXTRACT(MONTH FROM date)::INT  AS month,
        COALESCE(SUM(amount) FILTER (WHERE type = 'income'),  0) AS income,
        COALESCE(SUM(amount) FILTER (WHERE type = 'expense'), 0) AS expense,
        COALESCE(SUM(amount) FILTER (WHERE type = 'savings'), 0) AS savings,
        COALESCE(SUM(amount) FILTER (WHERE type = 'income'),  0)
            - COALESCE(SUM(amount) FILTER (WHERE type = 'expense'), 0) AS balance
    FROM transactions
    WHERE family_id = p_family_id
      AND project_id IS NULL
    GROUP BY year, month
    ORDER BY year DESC, month DESC;
$$;
