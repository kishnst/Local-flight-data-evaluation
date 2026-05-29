"""Database access and KPI helpers for the BLR Streamlit dashboard."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

load_dotenv()

WindowType = Literal["24h", "7d", "30d"]

WINDOW_INTERVALS: dict[WindowType, str] = {
    "24h": "24 hours",
    "7d": "7 days",
    "30d": "30 days",
}


def get_database_url() -> str:
    host = os.environ["DB_HOST"]
    port = os.environ["DB_PORT"]
    name = os.environ["DB_NAME"]
    user = os.environ["DB_USER"]
    password = quote_plus(os.environ["DB_PASSWORD"])
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(get_database_url(), pool_pre_ping=True)


def window_interval(window: WindowType) -> str:
    return WINDOW_INTERVALS[window]


def _airline_clause(airline_iata: str | None, prefix: str = "") -> tuple[str, dict]:
    if not airline_iata or airline_iata == "All Airlines":
        return "", {}
    col = f"{prefix}airline_iata" if prefix else "airline_iata"
    return f" AND {col} = :airline_iata", {"airline_iata": airline_iata}


def fetch_overview_kpis(window: WindowType, airline_iata: str | None) -> dict:
    """Overall OTA %, avg arrival delay, flight count, cancellation rate."""
    airline_sql, airline_params = _airline_clause(airline_iata)
    sql = text(
        f"""
        WITH base AS (
            SELECT *
            FROM flight_kpi_base
            WHERE GREATEST(dep_event_ts, arr_event_ts) >= NOW() - INTERVAL '{window_interval(window)}'
            {airline_sql}
        )
        SELECT
            COUNT(*) AS total_flights,
            COUNT(*) FILTER (WHERE flight_status = 'cancelled') AS cancelled_flights,
            COUNT(*) FILTER (
                WHERE actual_arrival IS NOT NULL
                  AND ops_status_normalized = 'ARRIVED'
            ) AS arr_eligible,
            COUNT(*) FILTER (
                WHERE actual_arrival IS NOT NULL
                  AND ops_status_normalized = 'ARRIVED'
                  AND arrival_delay_min <= 15
            ) AS arr_on_time,
            AVG(arrival_delay_min) FILTER (
                WHERE arrival_delay_min IS NOT NULL
            ) AS avg_arrival_delay_min
        FROM base
        """
    )
    with get_engine().connect() as conn:
        row = conn.execute(sql, airline_params).mappings().one()

    total = int(row["total_flights"] or 0)
    cancelled = int(row["cancelled_flights"] or 0)
    arr_eligible = int(row["arr_eligible"] or 0)
    arr_on_time = int(row["arr_on_time"] or 0)

    ota_pct = (100.0 * arr_on_time / arr_eligible) if arr_eligible else None
    cancel_pct = (100.0 * cancelled / total) if total else 0.0
    avg_delay = float(row["avg_arrival_delay_min"]) if row["avg_arrival_delay_min"] is not None else None

    return {
        "total_flights": total,
        "ota_pct": ota_pct,
        "avg_arrival_delay_min": avg_delay,
        "cancellation_rate_pct": cancel_pct,
    }


def fetch_airline_rankings(window: WindowType, airline_iata: str | None) -> pd.DataFrame:
    """Per-airline KPIs and composite score (min 5 flights for ranking)."""
    airline_sql, airline_params = _airline_clause(airline_iata)
    sql = text(
        f"""
        WITH base AS (
            SELECT *
            FROM flight_kpi_base
            WHERE GREATEST(dep_event_ts, arr_event_ts) >= NOW() - INTERVAL '{window_interval(window)}'
            {airline_sql}
        ),
        per_airline AS (
            SELECT
                airline_iata,
                MAX(airline_name) AS airline_name,
                COUNT(*) AS flights,
                COUNT(*) FILTER (
                    WHERE actual_arrival IS NOT NULL
                      AND ops_status_normalized = 'ARRIVED'
                ) AS arr_denom,
                COUNT(*) FILTER (
                    WHERE actual_arrival IS NOT NULL
                      AND ops_status_normalized = 'ARRIVED'
                      AND arrival_delay_min <= 15
                ) AS arr_on_time,
                COUNT(*) FILTER (
                    WHERE actual_departure IS NOT NULL
                      AND ops_status_normalized IN ('DEPARTED', 'ARRIVED')
                ) AS dep_denom,
                COUNT(*) FILTER (
                    WHERE actual_departure IS NOT NULL
                      AND ops_status_normalized IN ('DEPARTED', 'ARRIVED')
                      AND departure_delay_min <= 15
                ) AS dep_on_time,
                AVG(arrival_delay_min) FILTER (
                    WHERE arrival_delay_min IS NOT NULL
                ) AS avg_arrival_delay_min
            FROM base
            GROUP BY airline_iata
        ),
        max_delay AS (
            SELECT GREATEST(COALESCE(MAX(arrival_delay_min), 1), 1) AS max_delay
            FROM base
            WHERE arrival_delay_min IS NOT NULL
        )
        SELECT
            p.airline_iata,
            p.airline_name,
            p.flights,
            ROUND(100.0 * p.arr_on_time / NULLIF(p.arr_denom, 0), 2) AS ota_pct,
            ROUND(100.0 * p.dep_on_time / NULLIF(p.dep_denom, 0), 2) AS otd_pct,
            ROUND(p.avg_arrival_delay_min::NUMERIC, 2) AS avg_delay_min,
            ROUND(
                (
                    0.40 * COALESCE(100.0 * p.arr_on_time / NULLIF(p.arr_denom, 0), 0)
                    + 0.30 * COALESCE(100.0 * p.dep_on_time / NULLIF(p.dep_denom, 0), 0)
                    + 0.30 * (
                        100.0 - COALESCE(p.avg_arrival_delay_min, 0)
                        / m.max_delay * 100.0
                    )
                )::NUMERIC,
                2
            ) AS score
        FROM per_airline p
        CROSS JOIN max_delay m
        WHERE p.flights >= 5
        ORDER BY score DESC NULLS LAST
        """
    )
    with get_engine().connect() as conn:
        df = pd.read_sql(sql, conn, params=airline_params)

    if df.empty:
        return df

    df.insert(0, "Rank", range(1, len(df) + 1))
    df = df.rename(
        columns={
            "airline_name": "Airline Name",
            "flights": "Flights",
            "ota_pct": "OTA %",
            "otd_pct": "OTD %",
            "avg_delay_min": "Avg Delay",
            "score": "Score",
        }
    )
    return df


def fetch_route_performance(
    window: WindowType,
    airline_iata: str | None,
    *,
    top_n: int = 10,
    worst_n: int = 5,
    min_flights: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    airline_sql, airline_params = _airline_clause(airline_iata)
    sql = text(
        f"""
        WITH base AS (
            SELECT *
            FROM flight_kpi_base
            WHERE GREATEST(dep_event_ts, arr_event_ts) >= NOW() - INTERVAL '{window_interval(window)}'
            {airline_sql}
        ),
        routes AS (
            SELECT
                route,
                COUNT(*) AS flights,
                ROUND(
                    100.0 * COUNT(*) FILTER (
                        WHERE actual_arrival IS NOT NULL
                          AND ops_status_normalized = 'ARRIVED'
                          AND arrival_delay_min <= 15
                    ) / NULLIF(
                        COUNT(*) FILTER (
                            WHERE actual_arrival IS NOT NULL
                              AND ops_status_normalized = 'ARRIVED'
                        ),
                        0
                    ),
                    2
                ) AS on_time_pct,
                ROUND(AVG(arrival_delay_min) FILTER (
                    WHERE arrival_delay_min IS NOT NULL
                )::NUMERIC, 2) AS avg_delay_min
            FROM base
            GROUP BY route
            HAVING COUNT(*) >= :min_flights
        )
        SELECT * FROM routes
        WHERE on_time_pct IS NOT NULL
        ORDER BY on_time_pct DESC
        """
    )
    params = {**airline_params, "min_flights": min_flights}
    with get_engine().connect() as conn:
        routes = pd.read_sql(sql, conn, params=params)

    if routes.empty:
        empty = pd.DataFrame(columns=["Route", "Flights", "On-Time %", "Avg Delay"])
        return empty, empty

    routes = routes.rename(
        columns={
            "route": "Route",
            "flights": "Flights",
            "on_time_pct": "On-Time %",
            "avg_delay_min": "Avg Delay",
        }
    )
    best = routes.head(top_n).copy()
    worst = routes.sort_values("On-Time %", ascending=True).head(worst_n).copy()
    return best, worst


def fetch_congestion_by_hour(window: WindowType, airline_iata: str | None) -> pd.DataFrame:
    """Average delay by hour (departures and arrivals at BLR combined)."""
    airline_sql, airline_params = _airline_clause(airline_iata)
    sql = text(
        f"""
        WITH base AS (
            SELECT *
            FROM flight_kpi_base
            WHERE GREATEST(dep_event_ts, arr_event_ts) >= NOW() - INTERVAL '{window_interval(window)}'
            {airline_sql}
        ),
        hourly AS (
            SELECT dep_hour AS hour, departure_delay_min AS delay_min, 'dep' AS leg
            FROM base
            WHERE dep_iata = 'BLR' AND departure_delay_min IS NOT NULL
            UNION ALL
            SELECT
                EXTRACT(HOUR FROM scheduled_arrival)::INT,
                arrival_delay_min,
                'arr'
            FROM base
            WHERE arr_iata = 'BLR' AND arrival_delay_min IS NOT NULL
        )
        SELECT
            hour,
            leg,
            COUNT(*) AS flights,
            ROUND(AVG(delay_min)::NUMERIC, 2) AS avg_delay_min
        FROM hourly
        WHERE hour BETWEEN 0 AND 23
        GROUP BY hour, leg
        ORDER BY hour, leg
        """
    )
    with get_engine().connect() as conn:
        return pd.read_sql(sql, conn, params=airline_params)


def fetch_peak_windows(hourly: pd.DataFrame) -> dict[str, str]:
    if hourly.empty:
        return {"departure": "N/A", "arrival": "N/A"}

    def peak_label(leg: str) -> str:
        subset = hourly[hourly["leg"] == leg]
        if subset.empty:
            return "N/A"
        row = subset.loc[subset["avg_delay_min"].idxmax()]
        return f"{int(row['hour']):02d}:00–{int(row['hour']):02d}:59 ({row['avg_delay_min']:.1f} min avg)"

    return {
        "departure": peak_label("dep"),
        "arrival": peak_label("arr"),
    }


def search_flights(
    query: str,
    window: WindowType,
    airline_iata: str | None,
    *,
    limit: int = 20,
) -> pd.DataFrame:
    q = (query or "").strip()
    airline_sql, airline_params = _airline_clause(airline_iata)
    pattern = f"%{q}%"
    sql = text(
        f"""
        SELECT
            flight_iata AS "Flight",
            airline_name AS "Airline",
            route AS "Route",
            flight_status AS "Status",
            ROUND(departure_delay_min::NUMERIC, 1) AS "Dep Delay (min)",
            ROUND(arrival_delay_min::NUMERIC, 1) AS "Arr Delay (min)",
            scheduled_departure AS "Sched Dep",
            actual_departure AS "Actual Dep",
            scheduled_arrival AS "Sched Arr",
            actual_arrival AS "Actual Arr"
        FROM flight_kpi_base
        WHERE GREATEST(dep_event_ts, arr_event_ts) >= NOW() - INTERVAL '{window_interval(window)}'
        {airline_sql}
        AND (
            :q = ''
            OR flight_iata ILIKE :pattern
            OR airline_name ILIKE :pattern
            OR airline_iata ILIKE :pattern
            OR route ILIKE :pattern
        )
        ORDER BY GREATEST(dep_event_ts, arr_event_ts) DESC
        LIMIT :lim
        """
    )
    params = {**airline_params, "q": q, "pattern": pattern, "lim": limit}
    with get_engine().connect() as conn:
        return pd.read_sql(sql, conn, params=params)


def list_airlines(window: WindowType) -> list[str]:
    sql = text(
        f"""
        SELECT DISTINCT airline_iata
        FROM flight_kpi_base
        WHERE GREATEST(dep_event_ts, arr_event_ts) >= NOW() - INTERVAL '{window_interval(window)}'
        ORDER BY airline_iata
        """
    )
    with get_engine().connect() as conn:
        rows = conn.execute(sql).scalars().all()
    return ["All Airlines", *rows]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_timestamp(dt: datetime | None = None) -> str:
    ts = dt or utc_now()
    return ts.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
