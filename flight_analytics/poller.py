from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timezone

from flight_analytics.client import AviationStackClient, AviationStackError
from flight_analytics.config import Settings
from flight_analytics.db import FlightRepository

logger = logging.getLogger(__name__)


class FlightPoller:
    """Poll AviationStack on a fixed interval and persist results."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: AviationStackClient | None = None,
        repository: FlightRepository | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or AviationStackClient(settings)
        self._repository = repository or FlightRepository(settings)
        self._running = True

    def stop(self) -> None:
        self._running = False

    def poll_once(self) -> int:
        ingested_at = datetime.now(timezone.utc)
        flights = self._client.fetch_all_flights()

        with self._repository.connect() as conn:
            self._repository.ensure_schema(conn)
            return self._repository.insert_flights(conn, flights, ingested_at=ingested_at)

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        logger.info(
            "Starting poller (interval=%ds, limit=%d)",
            self._settings.poll_interval_seconds,
            self._settings.aviationstack_limit,
        )

        while self._running:
            started = time.monotonic()
            try:
                count = self.poll_once()
                logger.info("Poll complete: %d records stored", count)
            except AviationStackError:
                logger.exception("AviationStack API error during poll")
            except Exception:
                logger.exception("Unexpected error during poll")

            if not self._running:
                break

            elapsed = time.monotonic() - started
            sleep_for = max(0.0, self._settings.poll_interval_seconds - elapsed)
            if sleep_for > 0 and self._running:
                time.sleep(sleep_for)

        logger.info("Poller stopped")

    def _handle_signal(self, signum: int, _frame: object) -> None:
        logger.info("Received signal %s, shutting down", signum)
        self.stop()
