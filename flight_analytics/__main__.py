from __future__ import annotations

import logging
import sys

from flight_analytics.config import Settings
from flight_analytics.poller import FlightPoller


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    try:
        settings = Settings.from_env()
    except ValueError as exc:
        logging.error("%s", exc)
        return 1

    FlightPoller(settings).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
