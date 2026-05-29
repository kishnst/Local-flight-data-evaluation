-- All 5 KPIs in one result set:
-- airline_iata, metric_name, metric_value, window_type, calculated_at
--
-- Prerequisites: sql/00_flight_kpi_base_view.sql
-- Run: psql ... -f sql/99_kpi_metrics_unified.sql

CREATE OR REPLACE VIEW v_kpi_metrics_unified AS
WITH windows AS (
    SELECT '24h'::TEXT AS window_type, NOW() - INTERVAL '24 hours' AS window_start
    UNION ALL SELECT '7d', NOW() - INTERVAL '7 days'
    UNION ALL SELECT '30d', NOW() - INTERVAL '30 days'
),
calc_at AS (
    SELECT NOW() AS calculated_at
),
-- KPI 1: on-time departure
dep_eligible AS (
    SELECT e.*, w.window_type, w.window_start
    FROM flight_kpi_base e
    CROSS JOIN windows w
    WHERE e.actual_departure IS NOT NULL
      AND e.ops_status_normalized IN ('DEPARTED', 'ARRIVED')
      AND e.dep_event_ts >= w.window_start
),
kpi1_airline AS (
    SELECT
        window_type,
        airline_iata,
        'on_time_departure_pct' AS metric_name,
        ROUND(
            100.0 * COUNT(*) FILTER (WHERE departure_delay_min <= 15)
            / NULLIF(COUNT(*), 0),
            2
        ) AS metric_value
    FROM dep_eligible
    GROUP BY window_type, airline_iata
),
kpi1_route AS (
    SELECT
        window_type,
        airline_iata,
        'on_time_departure_pct|route:' || route AS metric_name,
        ROUND(
            100.0 * COUNT(*) FILTER (WHERE departure_delay_min <= 15)
            / NULLIF(COUNT(*), 0),
            2
        ) AS metric_value
    FROM dep_eligible
    GROUP BY window_type, airline_iata, route
),
kpi1_hour AS (
    SELECT
        window_type,
        airline_iata,
        'on_time_departure_pct|hour:' || dep_hour::TEXT AS metric_name,
        ROUND(
            100.0 * COUNT(*) FILTER (WHERE departure_delay_min <= 15)
            / NULLIF(COUNT(*), 0),
            2
        ) AS metric_value
    FROM dep_eligible
    GROUP BY window_type, airline_iata, dep_hour
),
-- KPI 2: on-time arrival
arr_eligible AS (
    SELECT e.*, w.window_type, w.window_start
    FROM flight_kpi_base e
    CROSS JOIN windows w
    WHERE e.actual_arrival IS NOT NULL
      AND e.ops_status_normalized = 'ARRIVED'
      AND e.arr_event_ts >= w.window_start
),
kpi2 AS (
    SELECT
        window_type,
        airline_iata,
        'on_time_arrival_pct' AS metric_name,
        ROUND(
            100.0 * COUNT(*) FILTER (WHERE arrival_delay_min <= 15)
            / NULLIF(COUNT(*), 0),
            2
        ) AS metric_value
    FROM arr_eligible
    GROUP BY window_type, airline_iata
),
-- KPI 3 & 4: average delays
kpi3 AS (
    SELECT
        w.window_type,
        e.airline_iata,
        'avg_departure_delay_min' AS metric_name,
        ROUND(AVG(e.departure_delay_min)::NUMERIC, 2) AS metric_value
    FROM flight_kpi_base e
    CROSS JOIN windows w
    WHERE e.departure_delay_min IS NOT NULL
      AND e.dep_event_ts >= w.window_start
    GROUP BY w.window_type, e.airline_iata
),
kpi4 AS (
    SELECT
        w.window_type,
        e.airline_iata,
        'avg_arrival_delay_min' AS metric_name,
        ROUND(AVG(e.arrival_delay_min)::NUMERIC, 2) AS metric_value
    FROM flight_kpi_base e
    CROSS JOIN windows w
    WHERE e.arrival_delay_min IS NOT NULL
      AND e.arr_event_ts >= w.window_start
    GROUP BY w.window_type, e.airline_iata
),
-- KPI 5 building blocks
dep_s AS (
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
arr_s AS (
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
        AVG(e.arrival_delay_min) FILTER (WHERE e.arrival_delay_min IS NOT NULL) AS avg_arr_delay,
        COUNT(*) AS flight_count
    FROM flight_kpi_base e
    CROSS JOIN windows w
    WHERE e.arr_event_ts >= w.window_start
    GROUP BY w.window_type, e.airline_iata
),
max_d AS (
    SELECT
        w.window_type,
        GREATEST(COALESCE(MAX(e.arrival_delay_min), 1), 1) AS max_delay
    FROM flight_kpi_base e
    CROSS JOIN windows w
    WHERE e.arr_event_ts >= w.window_start
      AND e.arrival_delay_min IS NOT NULL
    GROUP BY w.window_type
),
scored AS (
    SELECT
        a.window_type,
        a.airline_iata,
        ROUND(
            (
                0.40 * COALESCE(100.0 * a.arr_on_time / NULLIF(a.arr_denom, 0), 0)
                + 0.30 * COALESCE(100.0 * d.dep_on_time / NULLIF(d.dep_denom, 0), 0)
                + 0.30 * (
                    100.0 - COALESCE(a.avg_arr_delay, 0) / m.max_delay * 100.0
                )
            )::NUMERIC,
            2
        ) AS composite_score
    FROM arr_s a
    JOIN dep_s d
        ON d.window_type = a.window_type AND d.airline_iata = a.airline_iata
    JOIN max_d m ON m.window_type = a.window_type
    WHERE a.flight_count >= 5
),
ranked AS (
    SELECT
        window_type,
        airline_iata,
        composite_score,
        RANK() OVER (
            PARTITION BY window_type
            ORDER BY composite_score DESC NULLS LAST
        ) AS airline_rank
    FROM scored
),
kpi5 AS (
    SELECT window_type, airline_iata, 'airline_composite_score' AS metric_name, composite_score AS metric_value
    FROM ranked
    UNION ALL
    SELECT window_type, airline_iata, 'airline_rank', airline_rank::NUMERIC
    FROM ranked
),
all_metrics AS (
    SELECT window_type, airline_iata, metric_name, metric_value FROM kpi1_airline
    UNION ALL SELECT window_type, airline_iata, metric_name, metric_value FROM kpi1_route
    UNION ALL SELECT window_type, airline_iata, metric_name, metric_value FROM kpi1_hour
    UNION ALL SELECT window_type, airline_iata, metric_name, metric_value FROM kpi2
    UNION ALL SELECT window_type, airline_iata, metric_name, metric_value FROM kpi3
    UNION ALL SELECT window_type, airline_iata, metric_name, metric_value FROM kpi4
    UNION ALL SELECT window_type, airline_iata, metric_name, metric_value FROM kpi5
)
SELECT
    m.airline_iata,
    m.metric_name,
    m.metric_value,
    m.window_type,
    c.calculated_at
FROM all_metrics m
CROSS JOIN calc_at c
WHERE m.metric_value IS NOT NULL;

-- Ad-hoc query (same output without persisting):
-- SELECT * FROM v_kpi_metrics_unified ORDER BY window_type, metric_name, airline_iata;
