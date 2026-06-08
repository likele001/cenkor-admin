#!/bin/bash
# =============================================================
# Cenkor Admin · 宝塔静态 dist 部署（lightmes 同款）
#
# 1. 构建 frontend/*/dist
# 2. Docker 只起后端 + PG + Redis + MinIO（不占 5174/5175）
# 3. 宝塔：站点根目录 = dist，伪静态 SPA，只反代 /api/
# =============================================================
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info() { echo -e "${GREEN}▸${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; exit 1; }

cd "$(dirname "$0")/.."

[ -f ".env.prod" ] || err "请先运行: bash scripts/gen-secrets.sh"

info "① 构建前端 dist..."
bash scripts/build-frontends.sh

info "② 启动后端栈（无前端容器）..."
command -v docker >/dev/null 2>&1 || err "需要 Docker 跑 PG/Redis/Backend"
docker compose -f docker-compose.baota-static.yml --env-file .env.prod build backend celery-worker
docker compose -f docker-compose.baota-static.yml --env-file .env.prod up -d

info "③ 数据库迁移 + seed..."
docker compose -f docker-compose.baota-static.yml exec -T backend alembic upgrade head
docker compose -f docker-compose.baota-static.yml exec -T backend python -m cenkor_admin.scripts.seed || true

info "④ 等待后端..."
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 2
  if curl -sf "http://127.0.0.1:${BACKEND_HOST_PORT:-8002}/api/health" >/dev/null 2>&1; then
    info "✓ 后端 http://127.0.0.1:${BACKEND_HOST_PORT:-8002}/api/health"
    break
  fi
done

echo ""
info "部署完成（lightmes 静态模式）"
echo ""
echo "  请在宝塔按 docs/BAOTA_STATIC_DEPLOY.md 配置："
echo ""
echo "  | 域名              | 根目录（dist）                              |"
echo "  |-------------------|---------------------------------------------|"
echo "  | admin.example.com | /www/wwwroot/cenkor-admin/frontend/admin-web/dist   |"
echo "  | portal.example.com| /www/wwwroot/cenkor-admin/frontend/portal-web/dist  |"
echo ""
echo "  每个站点：伪静态 SPA + location /api/ → 127.0.0.1:8002"
echo "  文档：docs/CORE_PLATFORM.md · docs/BAOTA_STATIC_DEPLOY.md"
echo "  可选官网扩展：docs/addons/WEBSITE_CMS.md"
warn "不要把整站 / 反代到 8002（会和 lightmes 一样出现 JSON Not Found）"
