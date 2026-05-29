#!/bin/bash
# PostgreSQL first-boot initialization
set -euo pipefail

echo "Initializing airline_analytics database..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE airflow;
    GRANT ALL PRIVILEGES ON DATABASE airflow TO ${POSTGRES_USER};
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/01_flights.sql

if [ -d /docker-entrypoint-initdb.d/sql ]; then
  for f in /docker-entrypoint-initdb.d/sql/*.sql; do
    echo "Applying $(basename "$f")..."
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$f"
  done
fi

echo "Database initialization complete."
