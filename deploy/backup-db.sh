#!/usr/bin/env bash
# ==============================================================================
# Stráž - Automated PostgreSQL Database Backup Script
# ==============================================================================
# Usage:
#   chmod +x backup-db.sh
#   ./backup-db.sh
#
# Recommended cron setup (daily at 03:00):
#   0 3 * * * /opt/straz/deploy/backup-db.sh >> /var/log/straz-backup.log 2>&1
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Load environment variables if .env exists
if [ -f "${ROOT_DIR}/.env" ]; then
    # shellcheck disable=SC1091
    source "${ROOT_DIR}/.env"
fi

BACKUP_DIR="${BACKUP_DIR:-${ROOT_DIR}/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
BACKUP_FILENAME="straz_backup_${TIMESTAMP}.sql.gz"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILENAME}"

POSTGRES_USER="${POSTGRES_USER:-straz}"
POSTGRES_DB="${POSTGRES_DB:-straz}"
CONTAINER_NAME="${POSTGRES_CONTAINER:-postgres}"

log() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*"
}

log "INFO: Starting Stráž PostgreSQL backup..."

# Ensure destination directory exists
mkdir -p "${BACKUP_DIR}"

# Execute pg_dump inside container and compress
if docker compose -f "${SCRIPT_DIR}/docker-compose.yml" ps --services --filter "status=running" | grep -q "^postgres$"; then
    log "INFO: Dumping database '${POSTGRES_DB}' from docker compose service '${CONTAINER_NAME}'..."
    docker compose -f "${SCRIPT_DIR}/docker-compose.yml" exec -T postgres \
        pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists --no-owner --no-privileges \
        | gzip -9 > "${BACKUP_PATH}"
else
    log "ERROR: Container '${CONTAINER_NAME}' is not running! Backup aborted."
    exit 1
fi

# Verify backup file size
if [ ! -s "${BACKUP_PATH}" ]; then
    log "ERROR: Backup file was created but is empty: ${BACKUP_PATH}"
    rm -f "${BACKUP_PATH}"
    exit 1
fi

FILESIZE=$(du -h "${BACKUP_PATH}" | cut -f1)
log "SUCCESS: Backup completed successfully: ${BACKUP_PATH} (${FILESIZE})"

# Prune old backups based on retention policy
log "INFO: Pruning backups older than ${RETENTION_DAYS} days in ${BACKUP_DIR}..."
find "${BACKUP_DIR}" -type f -name "straz_backup_*.sql.gz" -mtime +"${RETENTION_DAYS}" -exec rm -vf {} \;

log "INFO: All backup tasks completed successfully."
exit 0
