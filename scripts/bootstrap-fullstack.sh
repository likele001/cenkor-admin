#!/usr/bin/env bash
# Cenkor Admin · 全栈 Docker 一键部署
#
#   bash scripts/bootstrap-fullstack.sh
#
# 做三件事：
#   1. 没有 .env 就生成一份（随机密钥 + 自动填本机 IP）
#   2. 构建并启动全部容器：PostgreSQL + Redis + MinIO + 后端 + Celery + 三个前端
#   3. 等后端就绪，打印各访问地址与初始管理员口令
#
# 幂等：.env 已存在时沿用；重复执行只做重建与重启。
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_TEMPLATE="docker/fullstack/env.fullstack.example"
COMPOSE_BASE="docker compose -f docker-compose.fullstack.yml"

say()  { printf '\033[36m▸\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# ---------- 前置检查 ----------
command -v docker >/dev/null 2>&1 || die "未找到 docker，请先安装 Docker"
docker compose version >/dev/null 2>&1 || die "缺少 docker compose 插件（v2+）"

rand_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$1"
  else
    head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

detect_ip() {
  if hostname -I >/dev/null 2>&1; then
    hostname -I 2>/dev/null | awk '{print $1}'
  fi
}
IP="$(detect_ip || true)"

# 开发者门户（应用中心）是**闭源模块**，不在开源仓库中（见 .gitignore 的 frontend/developer-web/）。
# 这里自动探测：源码齐全就带上 developer profile 一起构建，公开 clone 则静默跳过。
if [ -d frontend/developer-web ]; then
  COMPOSE_BASE="$COMPOSE_BASE --profile developer"
  WITH_DEVELOPER=1
else
  WITH_DEVELOPER=0
fi

# ---------- 1. 生成 .env ----------
if [ -f .env ]; then
  say ".env 已存在，沿用现有配置（要重新生成请先删除 .env）"
else
  [ -f "$ENV_TEMPLATE" ] || die "缺少模板 $ENV_TEMPLATE"
  say "生成 .env（随机密钥）"

  PG_PW="$(rand_hex 16)"
  MINIO_PW="$(rand_hex 16)"
  SECRET="$(rand_hex 48)"

  awk -v pg="$PG_PW" -v mo="$MINIO_PW" -v sk="$SECRET" -v ip="$IP" '
    /^#POSTGRES_PASSWORD=/   { print "POSTGRES_PASSWORD=" pg; next }
    /^#MINIO_ROOT_PASSWORD=/ { print "MINIO_ROOT_PASSWORD=" mo; next }
    /^S3_SECRET_KEY=/        { print "S3_SECRET_KEY=" mo; next }
    /^#SECRET_KEY=/          { print "SECRET_KEY=" sk; next }
    /^PUBLIC_BASE_URL=/      { if (ip != "") print "PUBLIC_BASE_URL=http://" ip ":5185"; else print; next }
    /^CORS_ORIGINS=/         { if (ip != "") print "CORS_ORIGINS=http://" ip ":5185,http://" ip ":5192,http://" ip ":5175"; else print; next }
    { print }
  ' "$ENV_TEMPLATE" > .env

  [ -n "$(tail -c 1 .env)" ] && printf '\n' >> .env
  chmod 600 .env
  say "已写入 .env（权限 600，含随机 POSTGRES_PASSWORD / MINIO_ROOT_PASSWORD / SECRET_KEY）"
fi

env_get() {
  grep -E "^${1}=" .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r' || true
}

# ---------- 2. 构建并启动 ----------
say "构建镜像并启动容器（首次构建需数分钟，请耐心等待）"
$COMPOSE_BASE up -d --build

# ---------- 3. 等后端就绪 ----------
BACKEND_PORT="$(env_get FS_BACKEND_PORT)"; BACKEND_PORT="${BACKEND_PORT:-8001}"
ADMIN_PORT="$(env_get FS_ADMIN_WEB_PORT)"; ADMIN_PORT="${ADMIN_PORT:-5185}"
PORTAL_PORT="$(env_get FS_PORTAL_WEB_PORT)"; PORTAL_PORT="${PORTAL_PORT:-5192}"
DEV_PORT="$(env_get FS_DEVELOPER_WEB_PORT)"; DEV_PORT="${DEV_PORT:-5175}"

say "等待后端就绪：127.0.0.1:${BACKEND_PORT}/api/health"
ready=0
for _ in $(seq 1 60); do
  if curl -fsS -o /dev/null "http://127.0.0.1:${BACKEND_PORT}/api/health" 2>/dev/null; then
    ready=1
    break
  fi
  sleep 3
done
if [ "$ready" = 1 ]; then
  say "后端已就绪"
else
  warn "等待超时（后端可能仍在迁移/建表），请查看：$COMPOSE_BASE logs backend"
fi

# ---------- 4. 汇总输出 ----------
HOST="${IP:-localhost}"
echo
echo "======================== 部署完成 ========================"
echo "  管理后台    http://${HOST}:${ADMIN_PORT}"
echo "  用户中心    http://${HOST}:${PORTAL_PORT}"
if [ "${WITH_DEVELOPER:-0}" = 1 ]; then
  echo "  开发者门户  http://${HOST}:${DEV_PORT}"
fi
echo "  API 文档    http://${HOST}:${BACKEND_PORT}/api/docs"
echo "  健康检查    http://${HOST}:${BACKEND_PORT}/api/health"
echo "=========================================================="
if [ "${WITH_DEVELOPER:-0}" != 1 ]; then
  echo
  echo "  提示：未包含 frontend/developer-web（闭源的应用中心），已跳过开发者门户。"
  echo "        在源码齐全的机器上可加 --profile developer 启用。"
fi
echo
if $COMPOSE_BASE logs backend 2>/dev/null | grep -q "已创建管理员"; then
  $COMPOSE_BASE logs backend 2>/dev/null | grep -A 3 "已创建管理员" | tail -6 || true
  echo "  （口令只显示这一次，请立即登录并修改）"
else
  echo "  管理员账号 admin@cenkor.cn 已存在，未重复创建。"
  echo "  如需重置口令：$COMPOSE_BASE exec backend python -m cenkor_admin.scripts.seed"
fi
echo
echo "常用运维："
echo "  $COMPOSE_BASE ps            # 查看容器状态"
echo "  $COMPOSE_BASE logs -f backend"
echo "  $COMPOSE_BASE down          # 停止（保留数据卷）"
echo
