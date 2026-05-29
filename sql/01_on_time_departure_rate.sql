-- KPI 1: On-Time Departure Rate (%)
-- Eligible: actual departure present, status departed or arrived (active/landed/diverted).
-- On-time: departure_delay_min <= 15
-- Breakdowns: airline_iata, route, dep_hour
-- Output shape: airline_iata, metric_name, metric_value, window_type, calculated_at

WITH windows AS (
    SELECT '24h'::TEXT AS window_type, NOW() - INTERVAL '24 hours' AS window_start
    UNION ALL SELECT '7d', NOW() - INTERVAL '7 days'
    UNION ALL SELECT '30d', NOW() - INTERVAL '30 days'
),
eligible AS (
    SELECT *
    FROM flight_kpi_base b
    WHERE b.actual_departure IS NOT NULL
      AND b.ops_status_normalized IN ('DEPARTED', 'ARRIVED')
),
by_airline AS (
    SELECT
        w.window_type,
        e.airline_iata,
        COUNT(*)::NUMERIC AS denom,
        COUNT(*) FILTER (WHERE e.departure_delay_min <= 15)::NUMERIC AS on_time
    FROM eligible e
    CROSS JOIN windows w
    WHERE e.dep_event_ts >= w.window_start
    GROUP BY w.window_type, e.airline_iata
    HAVING COUNT(*) >= 1
),
by_route AS (
    SELECT
        w.window_type,
        e.airline_iata,
        e.route,
        COUNT(*)::NUMERIC AS denom,
        COUNT(*) FILTER (WHERE e.departure_delay_min <= 15)::NUMERIC AS on_time
    FROM eligible e
    CROSS JOIN windows w
    WHERE e.dep_event_ts >= w.window_start
    GROUP BY w.window_type, e.airline_iata, e.route
    HAVING COUNT(*) >= 1
),
by_hour AS (
    SELECT
        w.window_type,
        e.airline_iata,
        e.dep_hour,
        COUNT(*)::NUMERIC AS denom,
        COUNT(*) FILTER (WHERE e.departure_delay_min <= 15)::NUMERIC AS on_time
    FROM eligible e
    CROSS JOIN windows w
    WHERE e.dep_event_ts >= w.window_start
    GROUP BY w.window_type, e.airline_iata, e.dep_hour
    HAVING COUNT(*) >= 1
)
SELECT
    airline_iata,
    'on_time_departure_pct' AS metric_name,
    ROUND(100.0 * on_time / NULLIF(denom, 0), 2) AS metric_value,
    window_type,
    NOW() AS calculated_at
FROM by_airline
WHERE denom > 0

UNION ALL

SELECT
    airline_iata,
    'on_time_departure_pct|route:' || route AS metric_name,
    ROUND(100.0 * on_time / NULLIF(denom, 0), 2),
    window_type,
    NOW()
FROM by_route
WHERE denom > 0

UNION ALL

SELECT
    airline_iata,
    'on_time_departure_pct|hour:' || dep_hour::TEXT AS metric_name,
    ROUND(100.0 * on_time / NULLIF(denom, 0), 2),
    window_type,
    NOW()
FROM by_hour
WHERE denom > 0

ORDER BY window_type, airline_iata, metric_name;
