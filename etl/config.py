"""Shared configuration for ETL modules."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

SQL_DIR = Path(os.getenv("SQL_DIR", "/opt/sql"))
if not SQL_DIR.exists():
    SQL_DIR = Path(__file__).resolve().parents[1] / "sql"

AIRPORT_IATA = os.getenv("AIRPORT_IATA", "BLR")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
API_LIMIT = int(os.getenv("API_LIMIT", "100"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))
RETRY_BACKOFF_SECONDS = float(os.getenv("RETRY_BACKOFF_SECONDS", "2.0"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
MAX_PAGES_PER_DIRECTION = int(os.getenv("MAX_PAGES_PER_DIRECTION", "5"))
PAGE_DELAY_SECONDS = float(os.getenv("PAGE_DELAY_SECONDS", "1.0"))
FLIGHT_DATE = os.getenv("FLIGHT_DATE", "").strip() or None
API_BASE_URL = os.getenv("AVIATIONSTACK_BASE_URL", "http://api.aviationstack.com/v1")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def db_config() -> dict[str, str | int]:
    return {
        "host": require_env("DB_HOST"),
        "port": int(require_env("DB_PORT")),
        "dbname": require_env("DB_NAME"),
        "user": require_env("DB_USER"),
        "password": require_env("DB_PASSWORD"),
    }


def database_url() -> str:
    from urllib.parse import quote_plus

    cfg = db_config()
    password = quote_plus(str(cfg["password"]))
    return (
        f"postgresql+psycopg2://{cfg['user']}:{password}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"
    )
