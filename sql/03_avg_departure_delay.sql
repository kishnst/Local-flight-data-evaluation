-- KPI 3: Average Departure Delay (minutes)
-- AVG(departure_delay_min) where delay is defined (actual departure recorded)

WITH windows AS (
    SELECT '24h'::TEXT AS window_type, NOW() - INTERVAL '24 hours' AS window_start
    UNION ALL SELECT '7d', NOW() - INTERVAL '7 days'
    UNION ALL SELECT '30d', NOW() - INTERVAL '30 days'
),
eligible AS (
    SELECT *
    FROM flight_kpi_base b
    WHERE b.departure_delay_min IS NOT NULL
)
SELECT
    e.airline_iata,
    'avg_departure_delay_min' AS metric_name,
    ROUND(AVG(e.departure_delay_min)::NUMERIC, 2) AS metric_value,
    w.window_type,
    NOW() AS calculated_at
FROM eligible e
CROSS JOIN windows w
WHERE e.dep_event_ts >= w.window_start
GROUP BY w.window_type, e.airline_iata
HAVING COUNT(*) >= 1
ORDER BY window_type, airline_iata;
