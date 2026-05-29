"""Continuous ingestion loop (ingester service)."""

from __future__ import annotations

import logging
import sys
import time

import psycopg2
import requests

from etl.config import POLL_INTERVAL_SECONDS, AIRPORT_IATA
from etl.db import connect_pg, ensure_raw_schema
from etl.load_raw import run_extract_and_load

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ingester")


def run_forever() -> None:
    logger.info("Starting ingester (interval=%ds, airport=%s)", POLL_INTERVAL_SECONDS, AIRPORT_IATA)
    conn = connect_pg()
    ensure_raw_schema(conn)
    conn.close()

    while True:
        try:
            stats = run_extract_and_load()
            logger.info("Cycle complete: %s", stats)
        except requests.RequestException:
            logger.exception("API error; retrying next cycle")
        except psycopg2.Error:
            logger.exception("Database error; retrying next cycle")
        time.sleep(POLL_INTERVAL_SECONDS)
