#!/bin/bash
# 宿主机 uvicorn 模式：迁移 + seed（backend 不在 Docker 里时用）
set -euo pipefail

cd "$(dirname "$0")/.."
BACKEND_DIR="$PWD/backend"
ENV_FILE="${ENV_FILE:-.env.prod}"

env_val() {
  [ -f "$ENV_FILE" ] || return 0
  grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | sed 's/\r$//' || true
}

docker_env() {
  local container="$1" key="$2"
  docker inspect "$container" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
    | grep -E "^${key}=" | head -1 | cut -d= -f2- || true
}

DB_USER="$(env_val POSTGRES_USER)"
DB_USER="${DB_USER:-cenkor}"
DB_NAME="$(env_val POSTGRES_DB)"
DB_NAME="${DB_NAME:-cenkor}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_HOST_PORT:-5433}"
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_HOST_PORT:-6380}"

DB_PASS="$(docker_env cenkor-postgres POSTGRES_PASSWORD)"
DB_PASS="${DB_PASS:-$(env_val POSTGRES_PASSWORD)}"
DB_PASS="${DB_PASS:-li123456}"

REDIS_CMD="$(docker inspect cenkor-redis --format '{{join .Config.Cmd \" \"}}' 2>/dev/null || true)"
REDIS_PASSWORD=""
if echo "$REDIS_CMD" | grep -q requirepass; then
  REDIS_PASSWORD="$(env_val REDIS_PASSWORD)"
fi

export PYTHONPATH=src
export DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
export DATABASE_URL_SYNC="postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

if [ -n "$REDIS_PASSWORD" ]; then
  export REDIS_URL="redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/0"
else
  export REDIS_URL="redis://${REDIS_HOST}:${REDIS_PORT}/0"
fi

echo "▸ DATABASE_URL → ${DB_HOST}:${DB_PORT}/${DB_NAME}"
echo "▸ REDIS_URL    → ${REDIS_HOST}:${REDIS_PORT}"

cd "$BACKEND_DIR"
alembic upgrade head
python3 -m cenkor_admin.scripts.seed

echo "✓ 完成。重启后端: bash scripts/restart-backend-host.sh"
