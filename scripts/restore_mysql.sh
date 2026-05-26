#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 backups/scores-db-YYYYMMDD-HHMMSS.sql.gz" >&2
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_FILE="$1"

cd "${PROJECT_DIR}"

if [ ! -f ".env" ]; then
  echo "Missing .env file in ${PROJECT_DIR}" >&2
  exit 1
fi

if [ ! -f "${BACKUP_FILE}" ]; then
  echo "Backup file not found: ${BACKUP_FILE}" >&2
  exit 1
fi

set -a
source .env
set +a

gzip -dc "${BACKUP_FILE}" | docker compose exec -T mysql \
  mysql \
  -u"${MYSQL_USER}" \
  -p"${MYSQL_PASSWORD}" \
  "${MYSQL_DATABASE}"

echo "Backup restored from: ${BACKUP_FILE}"
