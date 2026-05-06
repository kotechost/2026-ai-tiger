#!/bin/bash
set -u

BASE_DIR="/mnt/hdd22t2/solihost/llm-system/llm-system-bsk"
BACKUP_ROOT="${BASE_DIR}/backup"
VECTOR_SRC="${BASE_DIR}/vector-data"
VECTOR_DST="${BACKUP_ROOT}/vector-data"
PG_DST="${BACKUP_ROOT}/postgresql"
LOG_FILE="${BACKUP_ROOT}/backup.log"

DATE_TAG="$(date +%Y-%m-%d)"
KEEP_DAYS=7

PG_CONTAINER="postgresql-bsk"
DB_NAME="bible"
DB_SCHEMA="bible_service"
DB_USER="solihost"
DB_PASSWORD='soli1234!'
TABLES=("bible_book_info" "bible_crawl_content")

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

mkdir -p "${VECTOR_DST}" "${PG_DST}"

log "===== Backup start (${DATE_TAG}) ====="

# 1) vector-data backup
VEC_DAY_DIR="${VECTOR_DST}/${DATE_TAG}"
mkdir -p "${VEC_DAY_DIR}"
if [ -d "${VECTOR_SRC}" ]; then
    if cp -a "${VECTOR_SRC}/." "${VEC_DAY_DIR}/" 2>>"${LOG_FILE}"; then
        log "vector-data backup OK -> ${VEC_DAY_DIR}"
    else
        log "vector-data backup FAILED"
    fi
else
    log "vector-data source not found: ${VECTOR_SRC}"
fi

# 2) PostgreSQL bible_book_info backup (schema + data)
PG_DAY_DIR="${PG_DST}/${DATE_TAG}"
mkdir -p "${PG_DAY_DIR}"
if docker ps --format '{{.Names}}' | grep -q "^${PG_CONTAINER}$"; then
    for TABLE in "${TABLES[@]}"; do
        DUMP_FILE="${PG_DAY_DIR}/${DB_SCHEMA}.${TABLE}.sql"
        if docker exec -e PGPASSWORD="${DB_PASSWORD}" "${PG_CONTAINER}" \
            pg_dump -U "${DB_USER}" -d "${DB_NAME}" \
            -t "${DB_SCHEMA}.${TABLE}" \
            --no-owner --no-privileges \
            > "${DUMP_FILE}" 2>>"${LOG_FILE}"; then
            log "postgres backup OK -> ${DUMP_FILE}"
        else
            log "postgres backup FAILED (${TABLE})"
            rm -f "${DUMP_FILE}"
        fi
    done
else
    log "postgres container not running: ${PG_CONTAINER}"
fi

# 3) Rotate: keep only last ${KEEP_DAYS} date folders in each target
rotate() {
    local target="$1"
    [ -d "${target}" ] || return 0
    # list YYYY-MM-DD dirs, sorted desc, drop newest KEEP_DAYS, remove rest
    find "${target}" -mindepth 1 -maxdepth 1 -type d \
        -regextype posix-extended -regex '.*/[0-9]{4}-[0-9]{2}-[0-9]{2}$' \
        -printf '%f\n' | sort -r | tail -n +$((KEEP_DAYS + 1)) | \
        while read -r old; do
            log "rotate: removing ${target}/${old}"
            rm -rf "${target:?}/${old}"
        done
}

rotate "${VECTOR_DST}"
rotate "${PG_DST}"

log "===== Backup end ====="
exit 0
