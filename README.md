# BLR Flight Analytics

Airline performance analytics for **Kempegowda International Airport (BLR)** with a containerized ETL pipeline, PostgreSQL warehouse, Apache Airflow scheduling, and a Streamlit dashboard. That's an enterprise architecture for a dataset that fits in an Excel sheet lol.

## Architecture
'''API -> ETL -> PostgreSQL -> Airflow -> Dashboard'''

```
AviationStack API
       │
       ├──────────────────────────────┐
       ▼                              ▼
  Ingester Service              Airflow DAG (*/15 min)
  (continuous poll)             extract → transform → load
       │                              │
       └──────────┬───────────────────┘
                  ▼
           PostgreSQL 16
         (airline_analytics)
                  │
       ┌──────────┴──────────┐
       ▼                     ▼
  KPI SQL views         Streamlit :8501
  (flight_kpi_base)     Dashboard
```

| Component | Role |
|-----------|------|
| **ingester** | Real-time extract + load into `flights` |
| **Airflow** | Scheduled ETL every 15 minutes |
| **etl/** | Modular Python: `extract`, `transform`, `load_raw`, `load_kpi` |
| **postgres** | Persistent store (`./data/postgres`) |
| **streamlit** | Operational dashboard |

## Quick start (Docker)

### 1. Configure environment

```bash
cp .env.docker.example .env
# Edit .env — set AVIATIONSTACK_API_KEY
```

### 2. Start the stack

```bash
docker compose up --build
```

### 3. Open services

| Service | URL |
|---------|-----|
| Streamlit dashboard | http://localhost:8501 |
| Airflow UI | http://localhost:8080 (admin / admin) |
| PostgreSQL | `localhost:5432` — db `airline_analytics`, user `dev`, password `dev` |

### 4. Stop

```bash
docker compose down
```

To reset database volume:

```bash
docker compose down
rm -rf data/postgres
```

## Project layout

```
app/                 Streamlit dashboard (hot-reload mounted)
ingester/            Continuous API ingestion service
etl/                 Modular ETL package (used by ingester + Airflow)
sql/                 Transform SQL (views, KPI definitions)
airflow/dags/        Scheduled DAGs
scripts/init-db/     Postgres first-boot initialization
data/postgres/       Database persistence volume
```

## ETL modules

| Module | Stage | Description |
|--------|-------|-------------|
| `etl/extract.py` | Extract | Fetch BLR flights from AviationStack |
| `etl/load_raw.py` | Load | Insert into `flights` (deduped) |
| `etl/transform.py` | Transform | Apply `sql/*.sql` views |
| `etl/load_kpi.py` | Load | `refresh_kpi_metrics()` snapshot |
| `etl/ingestion.py` | — | Continuous loop for ingester service |

Airflow DAG: `airflow/dags/blr_flight_etl_dag.py` — runs **extract → transform → load** every 15 minutes.

## Local development (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r app/requirements.txt

# Start Postgres (see docker-compose for credentials)
docker compose up postgres -d

# Ingest
export $(grep -v '^#' .env | xargs)
python -m etl.load_raw  # or legacy aviationstack_ingestion.py

# Dashboard
streamlit run app/app.py
```


## Legacy scripts

Root-level `aviationstack_ingestion.py`, `app.py`, and `utils.py` remain for reference; **Docker uses `app/` and `ingester/` + `etl/`**.
