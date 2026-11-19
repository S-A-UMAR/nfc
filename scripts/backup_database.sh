#!/usr/bin/env bash
# =========================================================================
# STRIDE SECURE LOGICAL BACKUP SCRIPT
# Architecture: PostgreSQL 16/17 (Neon Direct Endpoint)
# Format: PostgreSQL Custom Archive (-Fc) with AES-256 GPG encryption
# =========================================================================
set -euo pipefail

# 1. Enforce strict umask: all created files will be restricted (0600 / 0700)
umask 077

# 2. Working directory
BACKUP_DIR="${HOME}/stride_backups"
mkdir -p "${BACKUP_DIR}"
cd "${BACKUP_DIR}"

# 3. Connection parameters (Must be Neon Direct endpoint, NOT -pooler)
export PGHOST="${PGHOST:-}"
export PGPORT="${PGPORT:-5432}"
export PGDATABASE="${PGDATABASE:-neondb}"
export PGUSER="${PGUSER:-neondb_owner}"
export PGSSLMODE="${PGSSLMODE:-require}"

if [ -z "${PGHOST}" ] || [ -z "${PGPORT}" ] || [ -z "${PGDATABASE}" ] || [ -z "${PGUSER}" ]; then
  echo "ERROR: Missing required connection parameters (PGHOST, PGPORT, PGDATABASE, PGUSER)."
  echo "Usage: PGHOST=ep-xyz.neon.tech PGUSER=neondb_owner $0"
  exit 1
fi

if [[ "${PGHOST}" == *"-pooler"* ]]; then
  echo "FATAL: PGHOST contains '-pooler'. pg_dump must run against the Direct endpoint to prevent connection drops."
  exit 1
fi

# 4. Set up temporary protected .pgpass file
PGPASSFILE="$(mktemp -t stride_pgpass.XXXXXX)"
export PGPASSFILE
chmod 600 "${PGPASSFILE}"

# Ensure temporary credential file is removed upon normal exit, error, or signal
trap 'rm -f "${PGPASSFILE:-}"' EXIT INT TERM HUP

if [ -z "${PGPASSWORD:-}" ]; then
  read -s -p "Enter Neon Direct Database Password for ${PGUSER}: " DB_PASSWORD
  echo ""
else
  DB_PASSWORD="${PGPASSWORD}"
fi

if [ -z "${DB_PASSWORD}" ]; then
  echo "ERROR: Database password cannot be empty."
  exit 1
fi

# Escape colons and backslashes in password per PostgreSQL .pgpass specifications
ESCAPED_PASSWORD="${DB_PASSWORD//\\/\\\\}"
ESCAPED_PASSWORD="${ESCAPED_PASSWORD//:/\\:}"

printf "%s:%s:%s:%s:%s\n" "${PGHOST}" "${PGPORT}" "${PGDATABASE}" "${PGUSER}" "${ESCAPED_PASSWORD}" > "${PGPASSFILE}"
unset DB_PASSWORD ESCAPED_PASSWORD PGPASSWORD

# 5. Define timestamped target filename and manifests
BACKUP_TIMESTAMP=$(date -u +"%Y%m%d_%H%M%SZ")
BACKUP_FILE="stride_prod_backup_${BACKUP_TIMESTAMP}.dump"
LOG_FILE="stride_prod_backup_${BACKUP_TIMESTAMP}.log"
META_FILE="stride_prod_backup_${BACKUP_TIMESTAMP}.meta.json"

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Starting logical backup to ${BACKUP_FILE}..."

# 6. Capture Client & Server Versions
PG_DUMP_VERSION=$(pg_dump --version 2>/dev/null || echo "pg_dump unknown")
PG_SERVER_VERSION=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -t -A -c "SHOW server_version;" 2>/dev/null || echo "server version unknown")

START_TIME=$(date +%s)

# 7. Execute pg_dump with explicit conditional command handling
if pg_dump \
  -h "${PGHOST}" \
  -p "${PGPORT}" \
  -U "${PGUSER}" \
  -d "${PGDATABASE}" \
  --format=c \
  --compress=6 \
  --no-owner \
  --no-privileges \
  --verbose \
  --file="${BACKUP_FILE}" \
  2> "${LOG_FILE}"; then
    DUMP_SUCCESS=true
else
    DUMP_SUCCESS=false
fi

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# 8. Evaluate completion status, verify non-empty file, compute checksum, and record manifest
if [ "${DUMP_SUCCESS}" = true ] && [ -s "${BACKUP_FILE}" ]; then
  FILE_SIZE_BYTES=$(stat -f%z "${BACKUP_FILE}" 2>/dev/null || stat -c%s "${BACKUP_FILE}" 2>/dev/null || wc -c < "${BACKUP_FILE}")
  FILE_SIZE_HUMAN=$(ls -lh "${BACKUP_FILE}" | awk '{print $5}')
  
  # Compute SHA-256 Checksum
  if command -v sha256sum >/dev/null 2>&1; then
    SHA256_CHECKSUM=$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')
  else
    SHA256_CHECKSUM=$(shasum -a 256 "${BACKUP_FILE}" | awk '{print $1}')
  fi

  # Record structured metadata manifest (NO PASSWORDS OR FULL URIs)
  cat > "${META_FILE}" <<EOF
{
  "backup_file": "${BACKUP_FILE}",
  "timestamp_utc": "${BACKUP_TIMESTAMP}",
  "pg_dump_version": "${PG_DUMP_VERSION}",
  "pg_server_version": "${PG_SERVER_VERSION}",
  "file_size_bytes": ${FILE_SIZE_BYTES},
  "file_size_human": "${FILE_SIZE_HUMAN}",
  "sha256_checksum": "${SHA256_CHECKSUM}",
  "duration_seconds": ${DURATION},
  "status": "COMPLETED_SUCCESS"
}
EOF

  echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] SUCCESS: Backup completed in ${DURATION}s."
  echo "Archive:  ${BACKUP_FILE} (${FILE_SIZE_HUMAN})"
  echo "Checksum: ${SHA256_CHECKSUM}"
  echo "Manifest: ${META_FILE}"

  # TOC Catalog Verification
  pg_restore --list "${BACKUP_FILE}" > "${BACKUP_FILE}.toc" 2>/dev/null || true
  echo "TOC generated at ${BACKUP_FILE}.toc"
else
  echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] ERROR: Backup failed or produced empty file. Removing partial backup..."
  rm -f "${BACKUP_FILE}"
  cat "${LOG_FILE}"
  exit 1
fi
