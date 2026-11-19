#!/usr/bin/env bash
# =========================================================================
# STRIDE SAFE DATABASE RESTORATION SCRIPT
# Architecture: Restores Custom Archive (-Fc) into an isolated target DB
# Safety Rule: Target database must be brand new and verified empty.
# =========================================================================
set -euo pipefail

umask 077

export RESTORE_HOST="${RESTORE_HOST:-localhost}"
export RESTORE_PORT="${RESTORE_PORT:-5432}"
export RESTORE_USER="${RESTORE_USER:-postgres}"
export PGSSLMODE="${PGSSLMODE:-prefer}"

BACKUP_FILE="${1:-}"
if [ -z "${BACKUP_FILE}" ] || [ ! -f "${BACKUP_FILE}" ]; then
  echo "ERROR: Valid backup file path required. Usage: $0 <path_to_backup.dump>"
  exit 1
fi

# Safeguard: Prevent accidental execution against remote Neon production databases
if [[ "${RESTORE_HOST}" == *"neon.tech"* ]] && [ "${ALLOW_REMOTE_RESTORE:-0}" != "1" ]; then
  echo "FATAL: RESTORE_HOST points to a remote Neon database host (${RESTORE_HOST})."
  echo "Restoring directly against Neon infrastructure is blocked by default to prevent accidental data modification."
  echo "To perform a rehearsal restore into an isolated Neon staging branch, explicitly run with: ALLOW_REMOTE_RESTORE=1"
  exit 1
fi

# Define a unique timestamped recovery database name
RESTORE_TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RESTORE_DB="stride_recovery_${RESTORE_TIMESTAMP}"
RESTORE_LOG="stride_restore_${RESTORE_TIMESTAMP}.log"

# Set up temporary protected .pgpass file
PGPASSFILE="$(mktemp -t stride_restore_pgpass.XXXXXX)"
export PGPASSFILE
chmod 600 "${PGPASSFILE}"
trap 'rm -f "${PGPASSFILE:-}"' EXIT INT TERM HUP

if [ -z "${RESTORE_PASSWORD:-}" ]; then
  read -s -p "Enter Target Database Password for ${RESTORE_USER}: " DB_PASSWORD
  echo ""
else
  DB_PASSWORD="${RESTORE_PASSWORD}"
fi

if [ -z "${DB_PASSWORD}" ]; then
  echo "ERROR: Database password cannot be empty."
  exit 1
fi

# Escape colons and backslashes in password per PostgreSQL .pgpass specifications
ESCAPED_PASSWORD="${DB_PASSWORD//\\/\\\\}"
ESCAPED_PASSWORD="${ESCAPED_PASSWORD//:/\\:}"

printf "%s:%s:*:%s:%s\n" "${RESTORE_HOST}" "${RESTORE_PORT}" "${RESTORE_USER}" "${ESCAPED_PASSWORD}" > "${PGPASSFILE}"
unset DB_PASSWORD ESCAPED_PASSWORD RESTORE_PASSWORD

# 1. Create a brand-new, unique target database (fails if DB already exists)
echo "Creating unique recovery database: ${RESTORE_DB}..."
createdb -h "${RESTORE_HOST}" -p "${RESTORE_PORT}" -U "${RESTORE_USER}" "${RESTORE_DB}"

# 2. Explicitly verify the recovery database is completely empty
echo "Verifying ${RESTORE_DB} is empty..."
TABLE_COUNT=$(psql -h "${RESTORE_HOST}" -p "${RESTORE_PORT}" -U "${RESTORE_USER}" -d "${RESTORE_DB}" -t -A \
  -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';")

if [ "${TABLE_COUNT}" -ne 0 ]; then
  echo "FATAL: Database ${RESTORE_DB} is NOT empty (${TABLE_COUNT} public tables exist). Aborting restore."
  exit 1
fi

# 3. Execute pg_restore with explicit conditional command handling
echo "Restoring ${BACKUP_FILE} into ${RESTORE_DB}..."
if pg_restore \
  -h "${RESTORE_HOST}" \
  -p "${RESTORE_PORT}" \
  -U "${RESTORE_USER}" \
  -d "${RESTORE_DB}" \
  --exit-on-error \
  --no-owner \
  --no-privileges \
  --verbose \
  "${BACKUP_FILE}" > "${RESTORE_LOG}" 2>&1; then
    RESTORE_SUCCESS=true
else
    RESTORE_SUCCESS=false
fi

if [ "${RESTORE_SUCCESS}" != true ]; then
  echo "FATAL: pg_restore failed. Inspecting error log:"
  cat "${RESTORE_LOG}"
  exit 1
fi

echo "SUCCESS: Archive restored into ${RESTORE_DB}."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/verify_integrity.sql" ]; then
  echo "Executing automated data integrity verification on ${RESTORE_DB}..."
  psql -h "${RESTORE_HOST}" -p "${RESTORE_PORT}" -U "${RESTORE_USER}" -d "${RESTORE_DB}" -v ON_ERROR_STOP=1 -f "${SCRIPT_DIR}/verify_integrity.sql"
fi
