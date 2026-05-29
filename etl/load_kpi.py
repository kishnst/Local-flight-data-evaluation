"""Load: snapshot KPI metrics into kpi_metrics table."""

from __future__ import annotations

import logging

from sqlalchemy import text

from etl.db import get_engine

logger = logging.getLogger(__name__)


def run_load_kpi() -> dict[str, int]:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(text("SELECT refresh_kpi_metrics() AS n"))
        row = result.fetchone()
    inserted = int(row[0]) if row else 0
    logger.info("KPI load complete: %d rows inserted", inserted)
    return {"kpi_rows_inserted": inserted}
