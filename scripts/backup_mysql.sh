#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${PROJECT_DIR}/backups"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/scores-db-${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"
cd "${PROJECT_DIR}"

if [ ! -f ".env" ]; then
  echo "Missing .env file in ${PROJECT_DIR}" >&2
  exit 1
fi

set -a
source .env
set +a

docker compose exec -T mysql \
  mysqldump \
  -u"${MYSQL_USER}" \
  -p"${MYSQL_PASSWORD}" \
  --single-transaction \
  --no-tablespaces \
  --routines \
  --triggers \
  "${MYSQL_DATABASE}" \
  | gzip > "${BACKUP_FILE}"

find "${BACKUP_DIR}" -name "scores-db-*.sql.gz" -type f -mtime +14 -delete

echo "Backup saved: ${BACKUP_FILE}"
