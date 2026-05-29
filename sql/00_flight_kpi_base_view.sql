-- Base enrichment view for BLR flight KPIs.
-- Maps AviationStack statuses to operational DEPARTED / ARRIVED labels.
-- Run: psql ... -f sql/00_flight_kpi_base_view.sql

CREATE OR REPLACE VIEW flight_kpi_base AS
SELECT
    f.id,
    f.flight_iata,
    COALESCE(
        (regexp_match(f.flight_iata, '^([A-Z]{2,3})'))[1],
        LEFT(f.flight_iata, 2)
    ) AS airline_iata,
    f.airline_name,
    f.dep_iata,
    f.arr_iata,
    f.dep_iata || '-' || f.arr_iata AS route,
    EXTRACT(HOUR FROM f.scheduled_departure)::INT AS dep_hour,
    f.scheduled_departure,
    f.actual_departure,
    f.scheduled_arrival,
    f.actual_arrival,
    f.flight_status,
    -- AviationStack: landed -> ARRIVED; active/diverted -> DEPARTED
    CASE
        WHEN f.flight_status = 'landed' THEN 'ARRIVED'
        WHEN f.flight_status IN ('active', 'diverted') THEN 'DEPARTED'
        ELSE UPPER(COALESCE(f.flight_status, 'UNKNOWN'))
    END AS ops_status_normalized,
    EXTRACT(EPOCH FROM (f.actual_departure - f.scheduled_departure)) / 60.0
        AS departure_delay_min,
    EXTRACT(EPOCH FROM (f.actual_arrival - f.scheduled_arrival)) / 60.0
        AS arrival_delay_min,
    COALESCE(f.actual_departure, f.scheduled_departure) AS dep_event_ts,
    COALESCE(f.actual_arrival, f.scheduled_arrival) AS arr_event_ts,
    f.ingestion_time
FROM flights f
WHERE f.dep_iata = 'BLR' OR f.arr_iata = 'BLR';

COMMENT ON VIEW flight_kpi_base IS
    'Enriched flight facts: airline_iata, route, delays (minutes), ops status.';
