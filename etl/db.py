"""Database helpers."""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg2
from psycopg2.extensions import connection as PgConnection
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from etl.config import SQL_DIR, db_config, database_url

logger = logging.getLogger(__name__)

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


def connect_pg() -> PgConnection:
    return psycopg2.connect(**db_config())


def get_engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True)


def ensure_raw_schema(conn: PgConnection) -> None:
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
        cur.execute(CREATE_UNIQUE_INDEX_SQL)
    conn.commit()
    logger.info("Raw flights schema ready")


def run_sql_file(engine: Engine, path: Path) -> None:
    sql = path.read_text()
    with engine.begin() as conn:
        conn.execute(text(sql))
    logger.info("Applied SQL: %s", path.name)


def apply_sql_directory(engine: Engine, directory: Path | None = None) -> None:
    directory = directory or SQL_DIR
    if not directory.exists():
        raise FileNotFoundError(f"SQL directory not found: {directory}")
    for path in sorted(directory.glob("*.sql")):
        run_sql_file(engine, path)
