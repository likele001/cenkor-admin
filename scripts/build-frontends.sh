#!/bin/bash
# =============================================================
# Cenkor Admin · 构建全部前端（宝塔静态 dist 部署用）
# 与 lightmes 相同：站点根目录指向 dist，/api/ 反代后端
# =============================================================
set -e

cd "$(dirname "$0")/.."

# 同域反代 /api/ 时留空；独立 api 子域时可设 https://api.cenkor.cn
API_BASE="${VITE_API_BASE_URL:-}"

GREEN='\033[0;32m'
info() { echo -e "${GREEN}▸${NC} $1"; }

info "VITE_API_BASE_URL=${API_BASE:-（空，走同域 /api/）}"

info "构建 admin-web..."
cd frontend/admin-web
npm install --silent 2>/dev/null || npm install
VITE_API_BASE_URL="$API_BASE" npm run build

info "构建 portal-web..."
cd ../portal-web
npm install --silent 2>/dev/null || npm install
VITE_API_BASE_URL="$API_BASE" npm run build

info "构建 developer-web..."
cd ../developer-web
npm install --silent 2>/dev/null || npm install
VITE_API_BASE_URL="$API_BASE" npm run build

info "构建 landing-web（品牌落地页）..."
cd ../landing-web
npm install --silent 2>/dev/null || npm install
VITE_API_BASE_URL="$API_BASE" npm run build

# landing-web 产物同步到 nginx 实际服务的目录（admin.cenkor.cn/landing/ → frontend/landing/）
# 注意：landing-web/vite.config.ts 的 base 必须为 /landing/，否则同步后资源 404
info "同步 landing 产物到 frontend/landing/ ..."
cd ..
rsync -a --delete landing-web/dist/ landing/

cd ../..
info "完成"
echo ""
echo "  管理后台 dist: frontend/admin-web/dist"
echo "  用户中心 dist: frontend/portal-web/dist"
echo "  开发者中心 dist: frontend/developer-web/dist"
echo "  品牌落地页 dist: frontend/landing-web/dist（已同步到 frontend/landing/ 线上目录）"
echo ""
echo "宝塔建站根目录请指向上面的 dist 目录，详见 docs/baota_static_deploy.md"
