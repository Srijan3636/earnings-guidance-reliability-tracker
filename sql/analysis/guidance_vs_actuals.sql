-- Join extracted revenue guidance to the NEXT reported quarter's actual
-- revenue, using LAG() over each company's own reported_financials series
-- so the comparison lines up correctly per company regardless of exact
-- fiscal-quarter-end date alignment.
--
-- Scope note (see DECISIONS.md): stated_value is free text as spoken by
-- management (e.g. "0% to 2.0% sequential growth in constant currency"),
-- not a single clean number. This query surfaces the guidance and the
-- actual side by side for a human (or a Power BI viewer) to compare — it
-- does NOT attempt to auto-parse the range into a number and compute a
-- pass/fail delta. Building a real guidance-string parser (handling
-- ranges, "constant currency" qualifiers, YoY vs QoQ framing) is future
-- scope, not something to fake here.

WITH revenue_actuals AS (
    SELECT
        company_id,
        period_end,
        value AS actual_revenue,
        LAG(value) OVER (PARTITION BY company_id ORDER BY period_end) AS prior_actual_revenue,
        ROUND(
            100.0 * (value - LAG(value) OVER (PARTITION BY company_id ORDER BY period_end))
            / NULLIF(LAG(value) OVER (PARTITION BY company_id ORDER BY period_end), 0)
        , 2) AS actual_qoq_growth_pct
    FROM reported_financials
    WHERE metric_name = 'Total Revenue'
),
next_actual_after_guidance AS (
    -- Filtering to ra.period_end > t.call_date is the whole point of this
    -- CTE: without it, ROW_NUMBER()...ORDER BY period_end ASC just returns
    -- each company's EARLIEST period on file, regardless of when the call
    -- actually happened. Found this exact bug on first run against real
    -- data — see DECISIONS.md.
    SELECT
        g.guidance_id,
        g.company_id,
        t.quarter_label,
        t.call_date,
        g.stated_value,
        g.direction,
        g.confidence,
        g.source_excerpt,
        ra.period_end AS next_reported_period,
        ra.actual_qoq_growth_pct,
        ROW_NUMBER() OVER (
            PARTITION BY g.guidance_id
            ORDER BY ra.period_end ASC
        ) AS rn
    FROM guidance g
    JOIN transcripts t ON t.transcript_id = g.transcript_id
    LEFT JOIN revenue_actuals ra
        ON ra.company_id = g.company_id
        AND (t.call_date IS NULL OR ra.period_end > t.call_date)
    WHERE g.guidance_type = 'revenue'
)
SELECT
    c.ticker,
    c.name,
    n.quarter_label AS guidance_given_in_quarter,
    n.call_date AS guidance_call_date,
    n.stated_value AS guidance_stated_value,
    n.direction AS guidance_direction,
    n.confidence AS extraction_confidence,
    n.next_reported_period,
    n.actual_qoq_growth_pct AS actual_revenue_qoq_growth_pct,
    n.source_excerpt
FROM next_actual_after_guidance n
JOIN companies c ON c.company_id = n.company_id
WHERE n.rn = 1  -- nearest reported period after the guidance
ORDER BY c.ticker, n.quarter_label;
