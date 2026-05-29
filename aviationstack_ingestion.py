#!/usr/bin/env python3
"""
Poll AviationStack for Kempegowda International Airport (BLR) flights
and persist them to PostgreSQL.

Reference: https://docs.apilayer.com/aviationstack/docs/api-features
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv
from psycopg2.extensions import connection as PgConnection

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

API_BASE_URL = "http://api.aviationstack.com/v1"
AIRPORT_IATA = "BLR"
POLL_INTERVAL_SECONDS = 60
API_LIMIT = 100
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 2.0
REQUEST_TIMEOUT_SECONDS = 30

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("aviationstack_ingestion")

CREATE_TABLE_SQL = """
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
"""

CREATE_UNIQUE_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_flights_iata_sched_dep
ON flights (flight_iata, scheduled_departure);
"""

INSERT_SQL = """
INSERT INTO flights (
    flight_iata,
    airline_name,
    dep_iata,
    arr_iata,
    scheduled_departure,
    actual_departure,
    scheduled_arrival,
    actual_arrival,
    flight_status
) VALUES (
    %(flight_iata)s,
    %(airline_name)s,
    %(dep_iata)s,
    %(arr_iata)s,
    %(scheduled_departure)s,
    %(actual_departure)s,
    %(scheduled_arrival)s,
    %(actual_arrival)s,
    %(flight_status)s
)
ON CONFLICT (flight_iata, scheduled_departure) DO NOTHING;
"""


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def get_db_config() -> dict[str, str | int]:
    return {
        "host": _require_env("DB_HOST"),
        "port": int(_require_env("DB_PORT")),
        "dbname": _require_env("DB_NAME"),
        "user": _require_env("DB_USER"),
        "password": _require_env("DB_PASSWORD"),
    }


def get_api_key() -> str:
    return _require_env("AVIATIONSTACK_API_KEY")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def connect_db() -> PgConnection:
    cfg = get_db_config()
    logger.debug("Connecting to PostgreSQL at %s:%s/%s", cfg["host"], cfg["port"], cfg["dbname"])
    return psycopg2.connect(**cfg)


def create_table(conn: PgConnection) -> None:
    """Create the flights table and deduplication index if they do not exist."""
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
        cur.execute(CREATE_UNIQUE_INDEX_SQL)
    conn.commit()
    logger.info("Database schema is ready")


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def parse_timestamp(raw: str | None) -> datetime | None:
    """Parse AviationStack ISO-8601 timestamps for PostgreSQL."""
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    # AviationStack uses offsets like +00:00; fromisoformat handles them in 3.11+.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        logger.warning("Could not parse timestamp: %r", raw)
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _safe_str(value: Any, max_len: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len]


def normalize_flight(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Map AviationStack JSON to a flat row dict with null-safe fields."""
    departure = raw.get("departure") or {}
    arrival = raw.get("arrival") or {}
    airline = raw.get("airline") or {}
    flight = raw.get("flight") or {}

    dep_iata = _safe_str(departure.get("iata"), 10)
    arr_iata = _safe_str(arrival.get("iata"), 10)

    if dep_iata != AIRPORT_IATA and arr_iata != AIRPORT_IATA:
        return None

    flight_iata = _safe_str(flight.get("iata"), 20)
    scheduled_departure = parse_timestamp(departure.get("scheduled"))

    # flight_iata + scheduled_departure form the dedupe key; skip incomplete rows.
    if not flight_iata or scheduled_departure is None:
        logger.debug("Skipping flight with missing dedupe key: %s", raw)
        return None

    return {
        "flight_iata": flight_iata,
        "airline_name": _safe_str(airline.get("name"), 100),
        "dep_iata": dep_iata,
        "arr_iata": arr_iata,
        "scheduled_departure": scheduled_departure,
        "actual_departure": parse_timestamp(departure.get("actual")),
        "scheduled_arrival": parse_timestamp(arrival.get("scheduled")),
        "actual_arrival": parse_timestamp(arrival.get("actual")),
        "flight_status": _safe_str(raw.get("flight_status"), 50),
    }


def _request_with_retry(
    session: requests.Session,
    *,
    params: dict[str, str | int],
) -> list[dict[str, Any]]:
    """GET /flights with exponential backoff on transient failures."""
    url = f"{API_BASE_URL}/flights"
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)

            if response.status_code == 429:
                wait = RETRY_BACKOFF_SECONDS * attempt
                logger.warning(
                    "Rate limited (429); retrying in %.1fs (attempt %d/%d)",
                    wait,
                    attempt,
                    MAX_RETRIES,
                )
                time.sleep(wait)
                continue

            response.raise_for_status()
            payload = response.json()

            if payload.get("error"):
                code = payload["error"].get("code")
                message = payload["error"].get("message", "Unknown API error")
                raise requests.HTTPError(
                    f"AviationStack API error {code}: {message}",
                    response=response,
                )

            return payload.get("data") or []

        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt >= MAX_RETRIES:
                break
            wait = RETRY_BACKOFF_SECONDS * attempt
            logger.warning(
                "API request failed (%s); retrying in %.1fs (attempt %d/%d)",
                exc,
                wait,
                attempt,
                MAX_RETRIES,
            )
            time.sleep(wait)

    assert last_error is not None
    raise last_error


def _fetch_pages_for_filter(
    session: requests.Session,
    *,
    api_key: str,
    dep_iata: str | None = None,
    arr_iata: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch all pages for a single dep/arr filter."""
    results: list[dict[str, Any]] = []
    offset = 0

    while True:
        params: dict[str, str | int] = {
            "access_key": api_key,
            "limit": API_LIMIT,
            "offset": offset,
        }
        if dep_iata:
            params["dep_iata"] = dep_iata
        if arr_iata:
            params["arr_iata"] = arr_iata

        batch = _request_with_retry(session, params=params)
        if not batch:
            break

        results.extend(batch)
        if len(batch) < API_LIMIT:
            break
        offset += API_LIMIT

    return results


def fetch_flights() -> list[dict[str, Any]]:
    """
    Query AviationStack for BLR departures and arrivals, merge, and dedupe.

    Uses server-side filters (dep_iata / arr_iata) to minimize payload size
    and avoid rate limits from global flight pagination.
    """
    api_key = get_api_key()
    session = requests.Session()

    departing = _fetch_pages_for_filter(session, api_key=api_key, dep_iata=AIRPORT_IATA)
    arriving = _fetch_pages_for_filter(session, api_key=api_key, arr_iata=AIRPORT_IATA)

    seen: set[tuple[str, str, str, str]] = set()
    merged: list[dict[str, Any]] = []

    for raw in departing + arriving:
        flight = raw.get("flight") or {}
        departure = raw.get("departure") or {}
        key = (
            str(flight.get("iata") or ""),
            str(departure.get("scheduled") or ""),
            str((raw.get("arrival") or {}).get("iata") or ""),
            str(raw.get("flight_status") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(raw)

    logger.info(
        "Fetched %d departing + %d arriving BLR records (%d unique after merge)",
        len(departing),
        len(arriving),
        len(merged),
    )
    return merged


def insert_flights(conn: PgConnection, flights: list[dict[str, Any]]) -> int:
    """
    Insert normalized flight rows; skip duplicates via unique index.

    Returns the number of newly inserted rows.
    """
    rows: list[dict[str, Any]] = []
    for raw in flights:
        row = normalize_flight(raw)
        if row:
            rows.append(row)

    if not rows:
        logger.info("No insertable BLR flights in this batch")
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
        logger.exception("Insert failed; transaction rolled back")
        raise

    skipped = len(rows) - inserted
    logger.info("Inserted %d new rows (%d duplicates skipped)", inserted, skipped)
    return inserted


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def poll_once(conn: PgConnection) -> int:
    """Single poll cycle: fetch from API and persist."""
    flights = fetch_flights()
    return insert_flights(conn, flights)


def main() -> None:
    logger.info(
        "Starting BLR flight ingestion (interval=%ds, airport=%s)",
        POLL_INTERVAL_SECONDS,
        AIRPORT_IATA,
    )

    conn: PgConnection | None = None
    try:
        conn = connect_db()
        create_table(conn)

        while True:
            try:
                poll_once(conn)
            except requests.RequestException:
                logger.exception("API error during poll; will retry next cycle")
            except psycopg2.Error:
                logger.exception("Database error during poll; will retry next cycle")
                if conn and not conn.closed:
                    conn.rollback()

            logger.info("Sleeping %d seconds until next poll", POLL_INTERVAL_SECONDS)
            time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)
    finally:
        if conn and not conn.closed:
            conn.close()
            logger.info("Database connection closed")


if __name__ == "__main__":
    main()
