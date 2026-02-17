#!/usr/bin/env bash
set -euo pipefail

# Required: DATABASE_URL (postgresql://... or postgresql+psycopg://...)
if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is required."
  exit 1
fi

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/mtg_draft_app_${TIMESTAMP}.dump"

mkdir -p "${BACKUP_DIR}"

# pg_dump accepts libpq URLs; SQLAlchemy's +psycopg is not needed here.
PG_URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"

pg_dump \
  --format=custom \
  --file="${BACKUP_FILE}" \
  "${PG_URL}"

find "${BACKUP_DIR}" -type f -name "*.dump" -mtime +"${RETENTION_DAYS}" -delete

echo "Backup created: ${BACKUP_FILE}"
