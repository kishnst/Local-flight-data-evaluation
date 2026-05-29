from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _optional(name: str) -> str | None:
    value = os.getenv(name)
    return value if value else None


@dataclass(frozen=True)
class Settings:
    aviationstack_access_key: str
    aviationstack_base_url: str
    aviationstack_limit: int
    database_url: str
    poll_interval_seconds: int
    flight_status: str | None
    dep_iata: str | None
    arr_iata: str | None
    flight_date: str | None

    @classmethod
    def from_env(cls) -> Settings:
        access_key = os.getenv("AVIATIONSTACK_ACCESS_KEY")
        if not access_key:
            raise ValueError("AVIATIONSTACK_ACCESS_KEY is required")

        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is required")

        limit = int(os.getenv("AVIATIONSTACK_LIMIT", "100"))
        if limit < 1:
            raise ValueError("AVIATIONSTACK_LIMIT must be at least 1")

        poll_interval = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
        if poll_interval < 1:
            raise ValueError("POLL_INTERVAL_SECONDS must be at least 1")

        return cls(
            aviationstack_access_key=access_key,
            aviationstack_base_url=os.getenv(
                "AVIATIONSTACK_BASE_URL", "http://api.aviationstack.com/v1"
            ).rstrip("/"),
            aviationstack_limit=limit,
            database_url=database_url,
            poll_interval_seconds=poll_interval,
            flight_status=_optional("FLIGHT_STATUS"),
            dep_iata=_optional("DEP_IATA"),
            arr_iata=_optional("ARR_IATA"),
            flight_date=_optional("FLIGHT_DATE"),
        )
