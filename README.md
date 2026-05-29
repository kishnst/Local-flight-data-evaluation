# Flight Data Analytics

Poll [AviationStack](https://aviationstack.com/) for real-time flight data and store snapshots in PostgreSQL.

## Setup

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Create a `.env` file in the project root (see Configuration below). At minimum:

```bash
AVIATIONSTACK_ACCESS_KEY=your_access_key_here
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/flight_analytics
```

3. Create the database (example with Docker):

```bash
docker run -d --name flight-pg \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=flight_analytics \
  -p 5432:5432 \
  postgres:16
```

4. Run the poller (fetches every 60 seconds by default):

```bash
python -m flight_analytics
```

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `AVIATIONSTACK_ACCESS_KEY` | Yes | API access key |
| `DATABASE_URL` | Yes | PostgreSQL connection URL |
| `AVIATIONSTACK_BASE_URL` | No | API base URL (default `http://api.aviationstack.com/v1`) |
| `AVIATIONSTACK_LIMIT` | No | Page size per request (default `100`) |
| `POLL_INTERVAL_SECONDS` | No | Seconds between polls (default `60`) |
| `FLIGHT_STATUS` | No | Filter: scheduled, active, landed, etc. |
| `DEP_IATA` / `ARR_IATA` | No | Filter by airport |
| `FLIGHT_DATE` | No | Filter by date (`YYYY-MM-DD`) |

## Database schema

Apply the flight events schema (tables, indexes, and views):

```bash
psql "$DATABASE_URL" -f schema/flight_events.sql
```

- `poll_batches` — one row per poller cycle
- `flight_events` — append-only snapshots from each poll
- `flight_latest` — view of the newest state per flight
- `flight_status_changes` — view for status transition analysis

The Python poller currently uses an inline `flights` table in `flight_analytics/db.py`. Migrate to this schema when you are ready to wire `poll_batches` and `flight_events`.

## Module layout

- `flight_analytics/client.py` — AviationStack HTTP client with pagination
- `flight_analytics/db.py` — Schema creation and batch inserts
- `flight_analytics/poller.py` — Minute-interval polling loop
- `flight_analytics/config.py` — Environment-based settings

Each poll stores a batch of rows with a shared `ingested_at` timestamp plus the full API payload in `raw_payload` (JSONB) for analytics.
