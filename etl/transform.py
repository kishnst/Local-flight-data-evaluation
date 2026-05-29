"""Transform: apply SQL views and KPI definitions."""

from __future__ import annotations

import logging
from pathlib import Path

from etl.config import SQL_DIR
from etl.db import apply_sql_directory, get_engine, run_sql_file

logger = logging.getLogger(__name__)

# Ordered transforms (optimized: single pass for views)
TRANSFORM_FILES = [
    "00_flight_kpi_base_view.sql",
    "99_kpi_metrics_unified.sql",
    "refresh_kpi_metrics.sql",
]


def run_transform(sql_dir: Path | None = None) -> dict[str, str]:
    """Apply KPI SQL in dependency order."""
    directory = sql_dir or SQL_DIR
    engine = get_engine()

    for name in TRANSFORM_FILES:
        path = directory / name
        if not path.exists():
            raise FileNotFoundError(path)
        run_sql_file(engine, path)

    logger.info("Transform complete (%d SQL files)", len(TRANSFORM_FILES))
    return {"status": "ok", "files_applied": str(len(TRANSFORM_FILES))}
