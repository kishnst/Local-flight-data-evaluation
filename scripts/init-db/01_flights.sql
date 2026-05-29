-- Raw landing table for AviationStack flight events
CREATE TABLE IF NOT EXISTS flights (
    id SERIAL PRIMARY KEY,
    flight_iata VARCHAR(20),
    airline_name VARCHAR(100),
    dep_iata VARCHAR(10),
    arr_iata VARCHAR(10),
    scheduled_departure TIMESTAMP,
    actual_departure TIMESTAMP,
    scheduled_arrival TIMESTAMP,
    actual_arrival TIMESTAMP,
    flight_status VARCHAR(50),
    ingestion_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_flights_iata_sched_dep
    ON flights (flight_iata, scheduled_departure);
