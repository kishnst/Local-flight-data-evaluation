"""Load: persist raw flight rows into PostgreSQL."""

from __future__ import annotations

import logging
from typing import Any

from psycopg2.extensions import connection as PgConnection

from etl.db import connect_pg, ensure_raw_schema
from etl.extract import fetch_flights_from_api, normalize_flight

logger = logging.getLogger(__name__)

INSERT_SQL = """
INSERT INTO flights (
    flight_iata, airline_name, dep_iata, arr_iata,
    scheduled_departure, actual_departure, scheduled_arrival, actual_arrival,
    flight_status
) VALUES (
    %(flight_iata)s, %(airline_name)s, %(dep_iata)s, %(arr_iata)s,
    %(scheduled_departure)s, %(actual_departure)s, %(scheduled_arrival)s, %(actual_arrival)s,
    %(flight_status)s
)
ON CONFLICT (flight_iata, scheduled_departure) DO NOTHING;
"""


def insert_flights(conn: PgConnection, flights: list[dict[str, Any]]) -> int:
    rows = [normalize_flight(raw) for raw in flights]
    rows = [r for r in rows if r]
    if not rows:
        return 0

    inserted = 0
    try:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(INSERT_SQL, row)
                inserted += cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    logger.info("Loaded %d new rows (%d duplicates skipped)", inserted, len(rows) - inserted)
    return inserted


def run_load_raw(flights: list[dict[str, Any]] | None = None) -> dict[str, int]:
    """Extract (optional) + load raw flights."""
    conn = connect_pg()
    try:
        ensure_raw_schema(conn)
        batch = flights if flights is not None else fetch_flights_from_api()
        inserted = insert_flights(conn, batch)
        return {"extracted": len(batch), "inserted": inserted}
    finally:
        conn.close()


def run_extract_and_load() -> dict[str, int]:
    return run_load_raw()
