#!/bin/bash
# =============================================================
# Cenkor Admin · 一键部署脚本
# 用法：bash scripts/deploy.sh [--mode docker|baota|baota-static]
# =============================================================
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info() { echo -e "${GREEN}▸${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; exit 1; }

MODE="docker"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    docker|baota) MODE="$1"; shift ;;
    *) err "未知参数: $1（支持 --mode docker|baota|baota-static）" ;;
  esac
done

cd "$(dirname "$0")/.."

if [ "$MODE" = "baota-static" ]; then
  exec bash scripts/deploy-baota-static.sh
fi

COMPOSE_FILE="docker-compose.prod.yml"
if [ "$MODE" = "baota" ]; then
  COMPOSE_FILE="docker-compose.baota.yml"
fi

info "部署模式: $MODE ($COMPOSE_FILE)"

# 1. 检查环境
info "检查环境..."
command -v docker >/dev/null 2>&1 || err "请先安装 Docker"
command -v openssl >/dev/null 2>&1 || err "请先安装 openssl"
[ -f ".env.prod" ] || err "请先生成 .env.prod（运行 scripts/gen-secrets.sh）"

# 2. SSL 证书（仅 docker 自管 nginx 模式需要）
if [ "$MODE" = "docker" ]; then
  if [ ! -f "deploy/nginx/certs/fullchain.pem" ] || [ ! -f "deploy/nginx/certs/privkey.pem" ]; then
    warn "SSL 证书缺失（deploy/nginx/certs/）"
    echo "  方式 A：自签证书（仅测试用）：bash scripts/gen-selfsigned-cert.sh"
    echo "  方式 B：Let's Encrypt + certbot"
    read -p "是否自动生成自签证书用于测试？(y/N) " gen
    if [ "$gen" = "y" ] || [ "$gen" = "Y" ]; then
      bash scripts/gen-selfsigned-cert.sh
    else
      err "请先准备证书再部署"
    fi
  fi
else
  info "宝塔模式：SSL 由宝塔面板管理，跳过容器证书检查"
fi

# 3. 构建
info "构建镜像..."
docker compose -f "$COMPOSE_FILE" --env-file .env.prod build

# 4. 启动
info "启动服务..."
docker compose -f "$COMPOSE_FILE" --env-file .env.prod up -d

# 5. migration
info "运行数据库迁移..."
docker compose -f "$COMPOSE_FILE" exec -T backend alembic upgrade head

# 6. seed
info "初始化种子数据..."
docker compose -f "$COMPOSE_FILE" exec -T backend python -m cenkor_admin.scripts.seed || true

# 7. 健康检查
info "等待后端就绪..."
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 3
  if docker compose -f "$COMPOSE_FILE" exec -T backend curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
    info "✓ 后端健康检查通过"
    break
  fi
  echo "  等待中 ($((i*3))s)..."
done

echo ""
info "部署完成！"
echo ""
if [ "$MODE" = "baota" ]; then
  echo "  宝塔反代目标："
  echo "    后端  http://127.0.0.1:8002  → api.cenkor.cn"
  echo "    后台  http://127.0.0.1:5174  → admin.cenkor.cn"
  echo "  详见 docs/DOMAIN_SETUP.md 与 deploy/baota/"
else
  echo "  公网     https://cenkor.cn"
  echo "  后台     https://admin.cenkor.cn"
  echo "  API      https://api.cenkor.cn"
fi
echo ""
info "默认账号：admin@cenkor.cn / admin123（首次登录后请修改）"
