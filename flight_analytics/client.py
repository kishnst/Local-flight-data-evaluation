from __future__ import annotations

import logging
from typing import Any

import requests

from flight_analytics.config import Settings

logger = logging.getLogger(__name__)


class AviationStackError(Exception):
    """Raised when the AviationStack API returns an error."""


class AviationStackClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None) -> None:
        self._settings = settings
        self._session = session or requests.Session()

    def fetch_all_flights(self) -> list[dict[str, Any]]:
        """Fetch flights, following offset pagination until exhausted."""
        flights: list[dict[str, Any]] = []
        offset = 0
        limit = self._settings.aviationstack_limit

        while True:
            batch = self._fetch_page(offset=offset, limit=limit)
            if not batch:
                break
            flights.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

        logger.info("Fetched %d flight records from AviationStack", len(flights))
        return flights

    def _fetch_page(self, *, offset: int, limit: int) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {
            "access_key": self._settings.aviationstack_access_key,
            "limit": limit,
            "offset": offset,
        }
        if self._settings.flight_status:
            params["flight_status"] = self._settings.flight_status
        if self._settings.dep_iata:
            params["dep_iata"] = self._settings.dep_iata
        if self._settings.arr_iata:
            params["arr_iata"] = self._settings.arr_iata
        if self._settings.flight_date:
            params["flight_date"] = self._settings.flight_date

        url = f"{self._settings.aviationstack_base_url}/flights"
        response = self._session.get(url, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()

        if payload.get("error"):
            code = payload["error"].get("code")
            message = payload["error"].get("message", "Unknown API error")
            raise AviationStackError(f"AviationStack error {code}: {message}")

        pagination = payload.get("pagination") or {}
        logger.debug(
            "Page offset=%d limit=%d count=%s total=%s",
            offset,
            limit,
            pagination.get("count"),
            pagination.get("total"),
        )
        return payload.get("data") or []
