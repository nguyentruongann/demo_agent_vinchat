#!/bin/sh
set -eu

# Keep the database schema at the repo's latest Alembic revision.
# Set RUN_MIGRATIONS=false only when migrations are managed elsewhere.
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[startup] alembic upgrade head"
  alembic upgrade head
fi


# One-time bootstrap:
# - seed destination data
# - load normalized PostgreSQL data
# - rebuild Chroma index with current embedding contract
#
# Enable only when:
# - first deployment
# - changing embedding model
# - changing vector schema
#
if [ "${BOOTSTRAP_CORE_DATA:-false}" = "true" ]; then
  echo "[startup] seed destinations"
  python -m scripts.seed_destinations

  echo "[startup] load core data"
  python -m scripts.load_core

  echo "[startup] build knowledge index"
  python -m src.backend.services.ingest_postgres --reset
fi


# Normal production startup:
# Do not rebuild Chroma every restart because it will:
# - re-embed all documents
# - consume Gemini quota
# - increase startup time
#
# Keep disabled unless intentionally rebuilding index.
if [ "${REBUILD_CHROMA_ON_START:-false}" = "true" ]; then
  echo "[startup] rebuild Chroma index"
  python -m src.backend.services.ingest_postgres --reset
fi


exec uvicorn src.backend.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${UVICORN_WORKERS:-2}"