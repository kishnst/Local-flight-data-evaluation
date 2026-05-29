-- Flight events schema for AviationStack polling analytics
-- Apply: psql "$DATABASE_URL" -f schema/flight_events.sql

BEGIN;

-- ---------------------------------------------------------------------------
-- Types
-- ---------------------------------------------------------------------------

CREATE TYPE flight_status AS ENUM (
    'scheduled',
    'active',
    'landed',
    'cancelled',
    'incident',
    'diverted',
    'unknown'
);

CREATE TYPE poll_status AS ENUM (
    'running',
    'success',
    'failed'
);

-- ---------------------------------------------------------------------------
-- Poll batches (one row per poller cycle)
-- ---------------------------------------------------------------------------

CREATE TABLE poll_batches (
    id              BIGSERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    status          poll_status NOT NULL DEFAULT 'running',
    records_fetched INTEGER NOT NULL DEFAULT 0,
    records_stored  INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT,
    CONSTRAINT poll_batches_completed_after_start
        CHECK (completed_at IS NULL OR completed_at >= started_at)
);

CREATE INDEX idx_poll_batches_started_at ON poll_batches (started_at DESC);

-- ---------------------------------------------------------------------------
-- Flight events (immutable snapshot per flight per poll)
-- ---------------------------------------------------------------------------

CREATE TABLE flight_events (
    id                      BIGSERIAL PRIMARY KEY,
    poll_batch_id           BIGINT REFERENCES poll_batches (id) ON DELETE SET NULL,
    observed_at             TIMESTAMPTZ NOT NULL,

    -- Identity
    flight_date             DATE NOT NULL,
    flight_iata             TEXT,
    flight_icao             TEXT,
    flight_number           TEXT,
    airline_name            TEXT,
    airline_iata            TEXT,
    airline_icao            TEXT,

    -- Operational state at observation time
    flight_status           flight_status NOT NULL DEFAULT 'unknown',

    -- Departure
    dep_airport             TEXT,
    dep_timezone            TEXT,
    dep_iata                TEXT,
    dep_icao                TEXT,
    dep_terminal            TEXT,
    dep_gate                TEXT,
    dep_delay_minutes       INTEGER,
    dep_scheduled           TIMESTAMPTZ,
    dep_estimated           TIMESTAMPTZ,
    dep_actual              TIMESTAMPTZ,

    -- Arrival
    arr_airport             TEXT,
    arr_timezone            TEXT,
    arr_iata                TEXT,
    arr_icao                TEXT,
    arr_terminal            TEXT,
    arr_gate                TEXT,
    arr_baggage             TEXT,
    arr_delay_minutes       INTEGER,
    arr_scheduled           TIMESTAMPTZ,
    arr_estimated           TIMESTAMPTZ,
    arr_actual              TIMESTAMPTZ,

    -- Aircraft
    aircraft_registration   TEXT,
    aircraft_iata           TEXT,
    aircraft_icao           TEXT,
    aircraft_icao24         TEXT,

    -- Live position (when provided by API)
    live_updated            TIMESTAMPTZ,
    live_latitude           DOUBLE PRECISION,
    live_longitude          DOUBLE PRECISION,
    live_altitude_m         DOUBLE PRECISION,
    live_direction_deg      DOUBLE PRECISION,
    live_speed_horizontal   DOUBLE PRECISION,
    live_speed_vertical     DOUBLE PRECISION,
    live_is_ground          BOOLEAN,

    -- Full AviationStack payload for this observation
    raw_payload             JSONB NOT NULL,

    CONSTRAINT flight_events_dep_delay_non_negative
        CHECK (dep_delay_minutes IS NULL OR dep_delay_minutes >= 0),
    CONSTRAINT flight_events_arr_delay_non_negative
        CHECK (arr_delay_minutes IS NULL OR arr_delay_minutes >= 0),
    CONSTRAINT flight_events_has_identity
        CHECK (flight_iata IS NOT NULL OR flight_icao IS NOT NULL OR flight_number IS NOT NULL)
);

COMMENT ON TABLE flight_events IS
    'Append-only flight state snapshots; one row per flight per poll observation.';
COMMENT ON COLUMN flight_events.observed_at IS
    'UTC timestamp when this snapshot was ingested from AviationStack.';
COMMENT ON COLUMN flight_events.raw_payload IS
    'Unmodified JSON object returned by the AviationStack /flights endpoint.';

-- Time-series and analytics indexes
CREATE INDEX idx_flight_events_observed_at ON flight_events (observed_at DESC);
CREATE INDEX idx_flight_events_flight_date ON flight_events (flight_date DESC);
CREATE INDEX idx_flight_events_flight_iata ON flight_events (flight_iata, observed_at DESC);
CREATE INDEX idx_flight_events_status ON flight_events (flight_status, observed_at DESC);
CREATE INDEX idx_flight_events_dep_iata ON flight_events (dep_iata, observed_at DESC);
CREATE INDEX idx_flight_events_arr_iata ON flight_events (arr_iata, observed_at DESC);
CREATE INDEX idx_flight_events_poll_batch ON flight_events (poll_batch_id);
CREATE INDEX idx_flight_events_raw_payload ON flight_events USING GIN (raw_payload);

-- Natural key for deduping within a poll window (optional uniqueness per batch)
CREATE UNIQUE INDEX uq_flight_events_batch_identity
    ON flight_events (
        poll_batch_id,
        flight_date,
        COALESCE(flight_iata, flight_icao, flight_number),
        dep_scheduled
    )
    WHERE poll_batch_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Views
-- ---------------------------------------------------------------------------

-- Latest observed state per flight on a given operating date
CREATE OR REPLACE VIEW flight_latest AS
SELECT DISTINCT ON (
    flight_date,
    COALESCE(flight_iata, flight_icao, flight_number),
    dep_scheduled
)
    id,
    poll_batch_id,
    observed_at,
    flight_date,
    flight_iata,
    flight_icao,
    flight_number,
    airline_name,
    airline_iata,
    airline_icao,
    flight_status,
    dep_airport,
    dep_iata,
    dep_icao,
    dep_gate,
    dep_delay_minutes,
    dep_scheduled,
    dep_estimated,
    dep_actual,
    arr_airport,
    arr_iata,
    arr_icao,
    arr_gate,
    arr_delay_minutes,
    arr_scheduled,
    arr_estimated,
    arr_actual,
    live_latitude,
    live_longitude,
    live_altitude_m,
    live_is_ground
FROM flight_events
ORDER BY
    flight_date,
    COALESCE(flight_iata, flight_icao, flight_number),
    dep_scheduled,
    observed_at DESC;

COMMENT ON VIEW flight_latest IS
    'Most recent snapshot per flight (by date, identifier, and scheduled departure).';

-- Status transitions between consecutive observations
CREATE OR REPLACE VIEW flight_status_changes AS
SELECT
    flight_date,
    COALESCE(flight_iata, flight_icao, flight_number) AS flight_key,
    dep_scheduled,
    observed_at,
    flight_status,
    LAG(flight_status) OVER (
        PARTITION BY
            flight_date,
            COALESCE(flight_iata, flight_icao, flight_number),
            dep_scheduled
        ORDER BY observed_at
    ) AS previous_status
FROM flight_events;

COMMIT;
