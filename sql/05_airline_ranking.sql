-- KPI 5: Airline Ranking (composite score)
-- Score = 40% on_time_arr + 30% on_time_dep + 30% * (100 - avg_arr_delay / max_delay)
-- Rank 1-N per window; minimum 5 flights in window (arrival-eligible count)

WITH windows AS (
    SELECT '24h'::TEXT AS window_type, NOW() - INTERVAL '24 hours' AS window_start
    UNION ALL SELECT '7d', NOW() - INTERVAL '7 days'
    UNION ALL SELECT '30d', NOW() - INTERVAL '30 days'
),
dep_stats AS (
    SELECT
        w.window_type,
        e.airline_iata,
        COUNT(*) FILTER (
            WHERE e.actual_departure IS NOT NULL
              AND e.ops_status_normalized IN ('DEPARTED', 'ARRIVED')
        ) AS dep_denom,
        COUNT(*) FILTER (
            WHERE e.actual_departure IS NOT NULL
              AND e.ops_status_normalized IN ('DEPARTED', 'ARRIVED')
              AND e.departure_delay_min <= 15
        ) AS dep_on_time
    FROM flight_kpi_base e
    CROSS JOIN windows w
    WHERE e.dep_event_ts >= w.window_start
    GROUP BY w.window_type, e.airline_iata
),
arr_stats AS (
    SELECT
        w.window_type,
        e.airline_iata,
        COUNT(*) FILTER (
            WHERE e.actual_arrival IS NOT NULL
              AND e.ops_status_normalized = 'ARRIVED'
        ) AS arr_denom,
        COUNT(*) FILTER (
            WHERE e.actual_arrival IS NOT NULL
              AND e.ops_status_normalized = 'ARRIVED'
              AND e.arrival_delay_min <= 15
        ) AS arr_on_time,
        AVG(e.arrival_delay_min) FILTER (
            WHERE e.arrival_delay_min IS NOT NULL
        ) AS avg_arr_delay,
        COUNT(*) AS flight_count
    FROM flight_kpi_base e
    CROSS JOIN windows w
    WHERE e.arr_event_ts >= w.window_start
    GROUP BY w.window_type, e.airline_iata
),
window_max_delay AS (
    SELECT
        w.window_type,
        GREATEST(COALESCE(MAX(e.arrival_delay_min), 1), 1) AS max_delay
    FROM flight_kpi_base e
    CROSS JOIN windows w
    WHERE e.arr_event_ts >= w.window_start
      AND e.arrival_delay_min IS NOT NULL
    GROUP BY w.window_type
),
scores AS (
    SELECT
        a.window_type,
        a.airline_iata,
        a.flight_count,
        ROUND(
            100.0 * a.arr_on_time / NULLIF(a.arr_denom, 0),
            2
        ) AS on_time_arr_pct,
        ROUND(
            100.0 * d.dep_on_time / NULLIF(d.dep_denom, 0),
            2
        ) AS on_time_dep_pct,
        ROUND(a.avg_arr_delay::NUMERIC, 2) AS avg_arr_delay_min,
        ROUND(
            (
                0.40 * COALESCE(100.0 * a.arr_on_time / NULLIF(a.arr_denom, 0), 0)
                + 0.30 * COALESCE(100.0 * d.dep_on_time / NULLIF(d.dep_denom, 0), 0)
                + 0.30 * (
                    100.0 - (
                        COALESCE(a.avg_arr_delay, 0)
                        / wm.max_delay
                        * 100.0
                    )
                )
            )::NUMERIC,
            2
        ) AS composite_score
    FROM arr_stats a
    JOIN dep_stats d
        ON d.window_type = a.window_type
       AND d.airline_iata = a.airline_iata
    JOIN window_max_delay wm ON wm.window_type = a.window_type
    WHERE a.flight_count >= 5
),
ranked AS (
    SELECT
        s.*,
        RANK() OVER (
            PARTITION BY s.window_type
            ORDER BY s.composite_score DESC NULLS LAST
        ) AS airline_rank
    FROM scores s
)
SELECT
    airline_iata,
    'airline_composite_score' AS metric_name,
    composite_score AS metric_value,
    window_type,
    NOW() AS calculated_at
FROM ranked

UNION ALL

SELECT
    airline_iata,
    'airline_rank',
    airline_rank::NUMERIC,
    window_type,
    NOW()
FROM ranked

UNION ALL

SELECT
    airline_iata,
    'on_time_arrival_pct',
    on_time_arr_pct,
    window_type,
    NOW()
FROM ranked

UNION ALL

SELECT
    airline_iata,
    'on_time_departure_pct',
    on_time_dep_pct,
    window_type,
    NOW()
FROM ranked

UNION ALL

SELECT
    airline_iata,
    'avg_arrival_delay_min',
    avg_arr_delay_min,
    window_type,
    NOW()
FROM ranked
WHERE avg_arr_delay_min IS NOT NULL

ORDER BY window_type, metric_name, metric_value DESC;
