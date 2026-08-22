#!/bin/sh
set -eu

# Keep the database schema at the repo's latest Alembic revision.
# Set RUN_MIGRATIONS=false only when migrations are managed elsewhere.
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[startup] alembic upgrade head"
  alembic upgrade head
fi

# Optional one-time bootstrap for a brand-new Railway PostgreSQL database.
# Enable only when the DB has not been seeded/loaded yet.
if [ "${BOOTSTRAP_CORE_DATA:-false}" = "true" ]; then
  echo "[startup] seed destinations"
  python -m scripts.seed_destinations
  echo "[startup] load core data"
  python -m scripts.load_core
  echo "[startup] build knowledge index"
  python -m src.backend.services.ingest_postgres --reset
fi

# Optional rebuild of Chroma. For production, attach a Railway Volume to
# /app/storage so the index survives redeploys.
if [ "${REBUILD_CHROMA_ON_START:-false}" = "true" ]; then
  echo "[startup] rebuild Chroma index"
  python -m src.backend.services.ingest_postgres --reset
fi

exec uvicorn src.backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
