from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from flight_analytics.config import Settings

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS flights (
    id BIGSERIAL PRIMARY KEY,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    flight_date DATE,
    flight_status TEXT,
    airline_name TEXT,
    airline_iata TEXT,
    airline_icao TEXT,
    flight_number TEXT,
    flight_iata TEXT,
    flight_icao TEXT,
    dep_airport TEXT,
    dep_timezone TEXT,
    dep_iata TEXT,
    dep_icao TEXT,
    dep_terminal TEXT,
    dep_gate TEXT,
    dep_delay INTEGER,
    dep_scheduled TIMESTAMPTZ,
    dep_estimated TIMESTAMPTZ,
    dep_actual TIMESTAMPTZ,
    arr_airport TEXT,
    arr_timezone TEXT,
    arr_iata TEXT,
    arr_icao TEXT,
    arr_terminal TEXT,
    arr_gate TEXT,
    arr_baggage TEXT,
    arr_delay INTEGER,
    arr_scheduled TIMESTAMPTZ,
    arr_estimated TIMESTAMPTZ,
    arr_actual TIMESTAMPTZ,
    aircraft_registration TEXT,
    aircraft_iata TEXT,
    aircraft_icao TEXT,
    aircraft_icao24 TEXT,
    live_updated TIMESTAMPTZ,
    live_latitude DOUBLE PRECISION,
    live_longitude DOUBLE PRECISION,
    live_altitude DOUBLE PRECISION,
    live_direction DOUBLE PRECISION,
    live_speed_horizontal DOUBLE PRECISION,
    live_speed_vertical DOUBLE PRECISION,
    live_is_ground BOOLEAN,
    raw_payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_flights_ingested_at ON flights (ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_flights_flight_iata ON flights (flight_iata);
CREATE INDEX IF NOT EXISTS idx_flights_flight_date ON flights (flight_date);
"""

INSERT_SQL = """
INSERT INTO flights (
    ingested_at,
    flight_date,
    flight_status,
    airline_name,
    airline_iata,
    airline_icao,
    flight_number,
    flight_iata,
    flight_icao,
    dep_airport,
    dep_timezone,
    dep_iata,
    dep_icao,
    dep_terminal,
    dep_gate,
    dep_delay,
    dep_scheduled,
    dep_estimated,
    dep_actual,
    arr_airport,
    arr_timezone,
    arr_iata,
    arr_icao,
    arr_terminal,
    arr_gate,
    arr_baggage,
    arr_delay,
    arr_scheduled,
    arr_estimated,
    arr_actual,
    aircraft_registration,
    aircraft_iata,
    aircraft_icao,
    aircraft_icao24,
    live_updated,
    live_latitude,
    live_longitude,
    live_altitude,
    live_direction,
    live_speed_horizontal,
    live_speed_vertical,
    live_is_ground,
    raw_payload
) VALUES (
    %(ingested_at)s,
    %(flight_date)s,
    %(flight_status)s,
    %(airline_name)s,
    %(airline_iata)s,
    %(airline_icao)s,
    %(flight_number)s,
    %(flight_iata)s,
    %(flight_icao)s,
    %(dep_airport)s,
    %(dep_timezone)s,
    %(dep_iata)s,
    %(dep_icao)s,
    %(dep_terminal)s,
    %(dep_gate)s,
    %(dep_delay)s,
    %(dep_scheduled)s,
    %(dep_estimated)s,
    %(dep_actual)s,
    %(arr_airport)s,
    %(arr_timezone)s,
    %(arr_iata)s,
    %(arr_icao)s,
    %(arr_terminal)s,
    %(arr_gate)s,
    %(arr_baggage)s,
    %(arr_delay)s,
    %(arr_scheduled)s,
    %(arr_estimated)s,
    %(arr_actual)s,
    %(aircraft_registration)s,
    %(aircraft_iata)s,
    %(aircraft_icao)s,
    %(aircraft_icao24)s,
    %(live_updated)s,
    %(live_latitude)s,
    %(live_longitude)s,
    %(live_altitude)s,
    %(live_direction)s,
    %(live_speed_horizontal)s,
    %(live_speed_vertical)s,
    %(live_is_ground)s,
    %(raw_payload)s
)
"""


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _nested(record: dict[str, Any], key: str) -> dict[str, Any]:
    nested = record.get(key)
    return nested if isinstance(nested, dict) else {}


def flight_to_row(record: dict[str, Any], ingested_at: datetime) -> dict[str, Any]:
    departure = _nested(record, "departure")
    arrival = _nested(record, "arrival")
    airline = _nested(record, "airline")
    flight = _nested(record, "flight")
    aircraft = _nested(record, "aircraft")
    live = _nested(record, "live")

    flight_date = record.get("flight_date")
    parsed_date = datetime.strptime(flight_date, "%Y-%m-%d").date() if flight_date else None

    return {
        "ingested_at": ingested_at,
        "flight_date": parsed_date,
        "flight_status": record.get("flight_status"),
        "airline_name": airline.get("name"),
        "airline_iata": airline.get("iata"),
        "airline_icao": airline.get("icao"),
        "flight_number": str(flight["number"]) if flight.get("number") is not None else None,
        "flight_iata": flight.get("iata"),
        "flight_icao": flight.get("icao"),
        "dep_airport": departure.get("airport"),
        "dep_timezone": departure.get("timezone"),
        "dep_iata": departure.get("iata"),
        "dep_icao": departure.get("icao"),
        "dep_terminal": departure.get("terminal"),
        "dep_gate": departure.get("gate"),
        "dep_delay": departure.get("delay"),
        "dep_scheduled": _parse_ts(departure.get("scheduled")),
        "dep_estimated": _parse_ts(departure.get("estimated")),
        "dep_actual": _parse_ts(departure.get("actual")),
        "arr_airport": arrival.get("airport"),
        "arr_timezone": arrival.get("timezone"),
        "arr_iata": arrival.get("iata"),
        "arr_icao": arrival.get("icao"),
        "arr_terminal": arrival.get("terminal"),
        "arr_gate": arrival.get("gate"),
        "arr_baggage": arrival.get("baggage"),
        "arr_delay": arrival.get("delay"),
        "arr_scheduled": _parse_ts(arrival.get("scheduled")),
        "arr_estimated": _parse_ts(arrival.get("estimated")),
        "arr_actual": _parse_ts(arrival.get("actual")),
        "aircraft_registration": aircraft.get("registration"),
        "aircraft_iata": aircraft.get("iata"),
        "aircraft_icao": aircraft.get("icao"),
        "aircraft_icao24": aircraft.get("icao24"),
        "live_updated": _parse_ts(live.get("updated")),
        "live_latitude": live.get("latitude"),
        "live_longitude": live.get("longitude"),
        "live_altitude": live.get("altitude"),
        "live_direction": live.get("direction"),
        "live_speed_horizontal": live.get("speed_horizontal"),
        "live_speed_vertical": live.get("speed_vertical"),
        "live_is_ground": live.get("is_ground"),
        "raw_payload": Jsonb(record),
    }


class FlightRepository:
    def __init__(self, settings: Settings) -> None:
        self._database_url = settings.database_url

    def connect(self) -> Connection[Any]:
        return psycopg.connect(self._database_url, row_factory=dict_row)

    def ensure_schema(self, conn: Connection[Any]) -> None:
        conn.execute(SCHEMA_SQL)
        conn.commit()
        logger.info("Database schema is ready")

    def insert_flights(
        self,
        conn: Connection[Any],
        records: list[dict[str, Any]],
        *,
        ingested_at: datetime | None = None,
    ) -> int:
        if not records:
            return 0

        ts = ingested_at or datetime.now(timezone.utc)
        rows = [flight_to_row(record, ts) for record in records]

        with conn.cursor() as cur:
            cur.executemany(INSERT_SQL, rows)
        conn.commit()
        logger.info("Inserted %d flight records", len(rows))
        return len(rows)
