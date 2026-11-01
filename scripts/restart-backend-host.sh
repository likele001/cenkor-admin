#!/bin/bash
# 宿主机 uvicorn 重启（「裸进程 / systemd」路线专用）
#
# ⚠️ 本机生产不走这条路 —— 后端由宝塔「Python 项目」托管（auto_run=true 自愈）。
#    在宝塔托管环境下执行本脚本会与守护进程打架：kill 掉宝塔的进程后再 nohup 裸起一个，
#    宝塔守护认不出（用户/参数不匹配）→ 每 120 秒拉起一个新实例再杀掉，
#    并且裸起的实例会连到错误的 Redis 库（脚本缺省 db0，生产是 db5）。
#    因此下面加了运行前拦截，检测到宝塔托管时直接拒绝。
set -euo pipefail

cd "$(dirname "$0")/.."
BACKEND_DIR="$PWD/backend"
ENV_FILE="${ENV_FILE:-.env.prod}"
PORT="${BACKEND_HOST_PORT:-8002}"
LOG="${LOG:-/tmp/cenkor-uvicorn.log}"
PIDFILE="${PIDFILE:-/tmp/cenkor-uvicorn.pid}"

# ---- 宝塔托管检测：命中则拒绝执行，避免抢端口 / 连错库 ----
BAOTA_PID_DIR="/www/server/python_project/vhost/pids"
if [ -d "$BAOTA_PID_DIR" ]; then
  for f in "$BAOTA_PID_DIR"/*.pid; do
    [ -f "$f" ] || continue
    bp="$(tr -dc '0-9' < "$f" 2>/dev/null || true)"
    [ -n "$bp" ] || continue
    if ! kill -0 "$bp" 2>/dev/null; then continue; fi
    # 这个宝塔项目是否正占着我们要用的端口
    if ss -lntp 2>/dev/null | grep -q ":${PORT} .*pid=${bp},"; then
      echo "✗ 检测到宝塔「Python 项目」$(basename "$f" .pid) 正在托管端口 ${PORT}（pid ${bp}）。" >&2
      echo "" >&2
      echo "  本机生产必须由宝塔托管，手动重启会让守护进程失联。" >&2
      echo "  正确做法（任选其一）：" >&2
      echo "    1) 宝塔面板 → 网站 → Python 项目 → cenkor → 重启" >&2
      echo "    2) 命令行：kill ${bp}   然后不要手动拉起，等宝塔自愈（10~60s）" >&2
      echo "" >&2
      echo "  仅当确实要脱离宝塔、改走裸进程/systemd 路线时，显式跳过本检查：" >&2
      echo "    SKIP_BAOTA_GUARD=1 bash scripts/restart-backend-host.sh" >&2
      [ "${SKIP_BAOTA_GUARD:-0}" = "1" ] || exit 2
      echo "  （SKIP_BAOTA_GUARD=1，已跳过拦截，继续执行）" >&2
    fi
  done
fi

# Python 解释器：优先 venv（BACKEND_PYTHON 可覆盖），回退 PATH 上的 python3
PYTHON_BIN="${BACKEND_PYTHON:-/www/server/pyporject_evn/cenkor/bin/python3}"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="$(command -v python3)"

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
# 2026-09-25 起数据库已迁移为宿主机原生 PostgreSQL(5432)/Redis(6379)，docker cenkor-* 容器已停用
DB_PORT="${DB_HOST_PORT:-5432}"
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_HOST_PORT:-6379}"

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
export DATABASE_URL_SYNC="postgresql+psycopg2://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

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
nohup "$PYTHON_BIN" -m uvicorn cenkor_admin.main:app \
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
