#!/bin/bash
# 宿主机 uvicorn 重启（宝塔 baota-static 裸进程模式）
set -euo pipefail

cd "$(dirname "$0")/.."
BACKEND_DIR="$PWD/backend"
ENV_FILE="${ENV_FILE:-.env.prod}"
PORT="${BACKEND_HOST_PORT:-8002}"
LOG="${LOG:-/tmp/cenkor-uvicorn.log}"
PIDFILE="${PIDFILE:-/tmp/cenkor-uvicorn.pid}"

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

# 优先 Docker 容器内真实密码（.env.prod 可能与映射卷不一致）
DB_PASS="$(docker_env cenkor-postgres POSTGRES_PASSWORD)"
DB_PASS="${DB_PASS:-$(env_val POSTGRES_PASSWORD)}"
DB_PASS="${DB_PASS:-li123456}"

REDIS_CMD="$(docker inspect cenkor-redis --format '{{join .Config.Cmd \" \"}}' 2>/dev/null || true)"
REDIS_PASSWORD=""
if echo "$REDIS_CMD" | grep -q requirepass; then
  REDIS_PASSWORD="$(env_val REDIS_PASSWORD)"
fi

export PYTHONPATH=src
export APP_ENV="${APP_ENV:-production}"
export SECRET_KEY="$(env_val SECRET_KEY)"
[ -n "$SECRET_KEY" ] || export SECRET_KEY="dev-secret-change-me-32-bytes-min-abcdef0123456789"

S3_EP="$(env_val S3_ENDPOINT)"
S3_EP="${S3_EP/http:\/\/minio:9000/http://127.0.0.1:9002}"
S3_EP="${S3_EP:-http://127.0.0.1:9002}"
export S3_ENDPOINT="$S3_EP"
export S3_ACCESS_KEY="$(env_val S3_ACCESS_KEY)"
export S3_SECRET_KEY="$(env_val S3_SECRET_KEY)"
export S3_BUCKET_PUBLIC="$(env_val S3_BUCKET_PUBLIC)"
export S3_BUCKET_PRIVATE="$(env_val S3_BUCKET_PRIVATE)"
# MinIO 容器凭据（与 .env.prod 不一致时以容器为准）
MINIO_USER="$(docker_env cenkor-minio MINIO_ROOT_USER)"
MINIO_PASS="$(docker_env cenkor-minio MINIO_ROOT_PASSWORD)"
[ -n "$MINIO_USER" ] && export S3_ACCESS_KEY="$MINIO_USER"
[ -n "$MINIO_PASS" ] && export S3_SECRET_KEY="$MINIO_PASS"
[ -n "$S3_ACCESS_KEY" ] || export S3_ACCESS_KEY=minio
[ -n "$S3_SECRET_KEY" ] || export S3_SECRET_KEY=minio12345

export DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
export DATABASE_URL_SYNC="postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

if [ -n "$REDIS_PASSWORD" ]; then
  export REDIS_URL="redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/0"
else
  export REDIS_URL="redis://${REDIS_HOST}:${REDIS_PORT}/0"
fi

echo "▸ DATABASE_URL → ${DB_HOST}:${DB_PORT}/${DB_NAME}"
echo "▸ REDIS_URL    → ${REDIS_HOST}:${REDIS_PORT} (auth=$([ -n "$REDIS_PASSWORD" ] && echo yes || echo no))"

echo "▸ 停止旧进程 (port ${PORT})..."
if [ -f "$PIDFILE" ]; then
  old_pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
    kill "$old_pid" 2>/dev/null || true
    sleep 1
  fi
fi
while read -r pid; do
  [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
done < <(ss -tlnp 2>/dev/null | grep ":${PORT} " | grep -oP 'pid=\K[0-9]+' || true)
sleep 1

echo "▸ 启动 uvicorn → 127.0.0.1:${PORT}"
cd "$BACKEND_DIR"
nohup python3 -m uvicorn cenkor_admin.main:app \
  --host 127.0.0.1 \
  --port "$PORT" \
  --workers 2 \
  >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"

sleep 3
ok=0
for i in 1 2 3 4 5; do
  if curl -sf "http://127.0.0.1:${PORT}/api/health" >/dev/null \
     && curl -sf "http://127.0.0.1:${PORT}/api/v1/public/site" >/dev/null; then
    ok=1
    break
  fi
  sleep 2
done
if [ "$ok" = 1 ]; then
  echo "✓ 健康检查通过 http://127.0.0.1:${PORT}/api/health"
  echo "  日志: $LOG  PID: $(cat "$PIDFILE")"
else
  echo "✗ 启动失败，最近日志："
  tail -30 "$LOG" || true
  exit 1
fi
