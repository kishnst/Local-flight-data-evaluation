-- Materialize KPI results into a table (optional persistence).
-- Run after 00_flight_kpi_base_view.sql and 99_kpi_metrics_unified.sql

CREATE TABLE IF NOT EXISTS kpi_metrics (
    id BIGSERIAL PRIMARY KEY,
    airline_iata VARCHAR(10) NOT NULL,
    metric_name VARCHAR(120) NOT NULL,
    metric_value NUMERIC(12, 2) NOT NULL,
    window_type VARCHAR(10) NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kpi_metrics_lookup
    ON kpi_metrics (window_type, metric_name, airline_iata, calculated_at DESC);

CREATE OR REPLACE FUNCTION refresh_kpi_metrics()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    inserted_count INTEGER;
BEGIN
    INSERT INTO kpi_metrics (airline_iata, metric_name, metric_value, window_type, calculated_at)
    SELECT airline_iata, metric_name, metric_value, window_type, calculated_at
    FROM v_kpi_metrics_unified;

    GET DIAGNOSTICS inserted_count = ROW_COUNT;
    RETURN inserted_count;
END;
$$;

COMMENT ON FUNCTION refresh_kpi_metrics IS
    'Snapshot current KPI view into kpi_metrics. Returns rows inserted.';

-- Example: SELECT refresh_kpi_metrics();
-- Latest snapshot: SELECT DISTINCT ON (airline_iata, metric_name, window_type)
--   * FROM kpi_metrics ORDER BY airline_iata, metric_name, window_type, calculated_at DESC;
