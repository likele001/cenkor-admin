#!/bin/bash
# Cenkor Admin · 数据备份（PostgreSQL + MinIO 元数据）
set -e
cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-/www/backup/cenkor-admin}"
STAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

source .env.prod 2>/dev/null || source .env

info() { echo "▸ $1"; }

info "备份 PostgreSQL..."
docker compose -f docker-compose.baota.yml exec -T postgres \
  pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
  | gzip > "$BACKUP_DIR/pg_${STAMP}.sql.gz" 2>/dev/null || \
  PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump -h localhost -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
  | gzip > "$BACKUP_DIR/pg_${STAMP}.sql.gz"

info "备份 .env.prod（请妥善保管）..."
cp .env.prod "$BACKUP_DIR/env_${STAMP}.prod" 2>/dev/null || true

info "完成：$BACKUP_DIR"
ls -lh "$BACKUP_DIR" | tail -5
