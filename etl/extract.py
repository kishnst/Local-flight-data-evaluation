"""Extract: AviationStack API -> in-memory flight records."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests

from etl.config import (
    AIRPORT_IATA,
    API_BASE_URL,
    API_LIMIT,
    FLIGHT_DATE,
    MAX_PAGES_PER_DIRECTION,
    MAX_RETRIES,
    PAGE_DELAY_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    RETRY_BACKOFF_SECONDS,
    require_env,
)

logger = logging.getLogger(__name__)


def parse_timestamp(raw: str | None) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _safe_str(value: Any, max_len: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_len] if text else None


def normalize_flight(raw: dict[str, Any]) -> dict[str, Any] | None:
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
    if not flight_iata or scheduled_departure is None:
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


def _request_with_retry(session: requests.Session, params: dict[str, str | int]) -> list[dict[str, Any]]:
    url = f"{API_BASE_URL}/flights"
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code == 429:
                last_error = requests.HTTPError("429 Too Many Requests", response=response)
                if attempt >= MAX_RETRIES:
                    break
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                msg = payload["error"].get("message", "Unknown API error")
                raise requests.HTTPError(f"AviationStack: {msg}", response=response)
            return payload.get("data") or []
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt >= MAX_RETRIES:
                break
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    if last_error is not None:
        raise last_error
    raise requests.HTTPError("AviationStack request failed after retries")


def _fetch_pages(session: requests.Session, api_key: str, *, dep_iata: str | None = None, arr_iata: str | None = None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    offset = 0
    page = 0

    while True:
        page += 1
        if MAX_PAGES_PER_DIRECTION > 0 and page > MAX_PAGES_PER_DIRECTION:
            break

        params: dict[str, str | int] = {
            "access_key": api_key,
            "limit": API_LIMIT,
            "offset": offset,
        }
        if dep_iata:
            params["dep_iata"] = dep_iata
        if arr_iata:
            params["arr_iata"] = arr_iata
        if FLIGHT_DATE:
            params["flight_date"] = FLIGHT_DATE

        batch = _request_with_retry(session, params)
        if not batch:
            break
        results.extend(batch)
        if len(batch) < API_LIMIT:
            break
        offset += API_LIMIT
        if PAGE_DELAY_SECONDS > 0:
            time.sleep(PAGE_DELAY_SECONDS)

    return results


def fetch_flights_from_api() -> list[dict[str, Any]]:
    api_key = require_env("AVIATIONSTACK_API_KEY")
    session = requests.Session()

    departing = _fetch_pages(session, api_key, dep_iata=AIRPORT_IATA)
    arriving = _fetch_pages(session, api_key, arr_iata=AIRPORT_IATA)

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

    logger.info("Extracted %d unique BLR flights from API", len(merged))
    return merged


def run_extract() -> dict[str, int]:
    """Airflow/cron entrypoint: extract only, return counts."""
    flights = fetch_flights_from_api()
    return {"extracted": len(flights)}
