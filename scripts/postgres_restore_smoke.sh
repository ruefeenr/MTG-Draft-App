#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <backup-file.dump>"
  exit 1
fi

BACKUP_FILE="$1"
if [ ! -f "${BACKUP_FILE}" ]; then
  echo "Backup file not found: ${BACKUP_FILE}"
  exit 1
fi

# Required env vars:
# - RESTORE_DATABASE_URL: target DB for restore drill
# - FLASK_SECRET_KEY: app secret for smoke checks
if [ -z "${RESTORE_DATABASE_URL:-}" ]; then
  echo "RESTORE_DATABASE_URL is required."
  exit 1
fi
if [ -z "${FLASK_SECRET_KEY:-}" ]; then
  echo "FLASK_SECRET_KEY is required."
  exit 1
fi

PG_URL="${RESTORE_DATABASE_URL/postgresql+psycopg:/postgresql:}"

pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  --dbname="${PG_URL}" \
  "${BACKUP_FILE}"

DATABASE_URL="${RESTORE_DATABASE_URL}" flask --app run.py db upgrade

DATABASE_URL="${RESTORE_DATABASE_URL}" python -c "from app import create_app; app=create_app(); c=app.test_client(); r=c.get('/healthz'); assert r.status_code == 200 and r.get_json() == {'status': 'ok'}"

echo "Restore smoke successful on: ${RESTORE_DATABASE_URL}"
