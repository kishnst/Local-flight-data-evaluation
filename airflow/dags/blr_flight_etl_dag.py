"""
BLR Flight Analytics ETL DAG
Extract (API) -> Transform (SQL views) -> Load (KPI snapshot)
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator

# etl package mounted at /opt/etl in Airflow containers
sys.path.insert(0, "/opt/etl")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "etl"))


def _extract(**_context):
    from etl.load_raw import run_extract_and_load

    return run_extract_and_load()


def _transform(**_context):
    from etl.transform import run_transform

    return run_transform()


def _load(**_context):
    from etl.load_kpi import run_load_kpi

    return run_load_kpi()


default_args = {
    "owner": "flight-analytics",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="blr_flight_etl",
    description="Extract AviationStack BLR flights, transform KPI views, load metrics",
    default_args=default_args,
    schedule_interval="*/15 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["blr", "etl", "aviation"],
) as dag:
    extract = PythonOperator(
        task_id="extract_load_raw",
        python_callable=_extract,
        doc="Extract from AviationStack API and load into flights table",
    )
    transform = PythonOperator(
        task_id="transform_kpi_views",
        python_callable=_transform,
        doc="Apply SQL transforms (flight_kpi_base, v_kpi_metrics_unified)",
    )
    load = PythonOperator(
        task_id="load_kpi_metrics",
        python_callable=_load,
        doc="Snapshot KPIs into kpi_metrics table",
    )

    extract >> transform >> load
