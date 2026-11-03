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
# developer-web 是闭源商业资产（.gitignore 显式排除），开源仓库/CI 的干净 checkout 里不存在，
# 存在才构建：本地私有部署照样出包，CI 环境自动跳过，避免 cd 失败导致整个打包中断。
if [ -d ../developer-web ]; then
  cd ../developer-web
  npm install --silent 2>/dev/null || npm install
  VITE_API_BASE_URL="$API_BASE" npm run build
else
  info "跳过 developer-web（闭源商业资产，未随仓库分发）"
fi

info "构建 landing-web（品牌落地页）..."
cd ../landing-web
npm install --silent 2>/dev/null || npm install
VITE_API_BASE_URL="$API_BASE" npm run build

# landing-web 产物同步到 nginx 实际服务的目录（admin.cenkor.cn/landing/ → frontend/landing/）
# 注意：landing-web/vite.config.ts 的 base 必须为 /landing/，否则同步后资源 404
info "同步 landing 产物到 frontend/landing/ ..."
cd ..
# frontend/landing/ 是线上目录，里面除了 dist 产物，还放着**不参与构建**的静态资产：
#   · docs-content/  文档源（markdown，由站点运行时/知识库消费）
#   · docs/          文档站旧静态页
#   · advantages.html / ai-cms.html / deploy.html / docs.html / features.html
#                    （旧静态落地页，仍在 git 里、可能被外部链接引用）
#   · favicon.svg / og-image.png / robots.txt / sitemap.xml
# 这些在 dist 里不存在。过去直接 `rsync -a --delete` 会把它们全删掉，
# 后果是 package-core.sh 用 `git ls-files | tar` 打包时报
# `tar: frontend/landing/advantages.html: Cannot stat`，Release 流水线必挂
# （v0.5.0 / v0.5.1 / v0.5.2 三个版本都因此失败）。
# 所以 --delete 要配排除清单：只清理构建产物，不动手写资产。
rsync -a --delete \
  --exclude='/docs-content/' \
  --exclude='/docs/' \
  --exclude='/advantages.html' \
  --exclude='/ai-cms.html' \
  --exclude='/deploy.html' \
  --exclude='/docs.html' \
  --exclude='/features.html' \
  --exclude='/favicon.svg' \
  --exclude='/og-image.png' \
  --exclude='/robots.txt' \
  --exclude='/sitemap.xml' \
  landing-web/dist/ landing/

cd ../..
info "完成"
echo ""
echo "  管理后台 dist: frontend/admin-web/dist"
echo "  用户中心 dist: frontend/portal-web/dist"
echo "  开发者中心 dist: frontend/developer-web/dist"
echo "  品牌落地页 dist: frontend/landing-web/dist（已同步到 frontend/landing/ 线上目录）"
echo ""
echo "宝塔建站根目录请指向上面的 dist 目录，详见 docs/baota_static_deploy.md"
