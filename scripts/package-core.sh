#!/bin/bash
# =============================================================
# Cenkor Admin · 核心平台打包（不含官网 addon）
# 产出：release/cenkor-admin-core-<version>-<date>.tar.gz
# =============================================================
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info() { echo -e "${GREEN}▸${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="${PACKAGE_VERSION:-0.1.0}"
DATE="$(date +%Y%m%d)"
PKG_NAME="cenkor-admin-core-${VERSION}-${DATE}"
RELEASE_DIR="$ROOT/release"
STAGE="$(mktemp -d)"
DEST="$STAGE/$PKG_NAME"

SKIP_BUILD=false
for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=true ;;
    --help|-h)
      echo "用法: bash scripts/package-core.sh [--skip-build]"
      echo "  产出 release/${PKG_NAME}.tar.gz"
      exit 0
      ;;
  esac
done

mkdir -p "$RELEASE_DIR" "$DEST"

if [ "$SKIP_BUILD" = false ]; then
  info "构建前端 dist..."
  bash scripts/build-frontends.sh
else
  warn "跳过前端构建（使用现有 dist）"
fi

info "复制核心文件到临时目录..."
(
  cd "$ROOT"
  tar -c \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='.mypy_cache' \
    --exclude='.ruff_cache' \
    --exclude='.vite' \
    --exclude='.env' \
    --exclude='.env.prod' \
    --exclude='.env.local' \
    --exclude='./release' \
    --exclude='*.tar.gz' \
    --exclude='*.zip' \
    --exclude='.DS_Store' \
    --exclude='.user.ini' \
    --exclude='.well-known' \
    --exclude='deploy/addons' \
    --exclude='deploy/website' \
    --exclude='docs/addons' \
    --exclude='deploy/examples' \
    --exclude='deploy/nginx/snippets' \
    --exclude='docker-compose.addon-website.yml' \
    --exclude='docs/DOMAIN_SETUP.md' \
    .
) | tar -x -C "$DEST"

info "写入安装说明 PACKAGE.md..."
cat > "$DEST/PACKAGE.md" <<EOF
# Cenkor Admin Core ${VERSION}

打包时间：$(date -Iseconds)  
类型：**核心平台**（admin-web + portal-web + backend），不含官网 addon。

## 目录

| 路径 | 说明 |
|------|------|
| \`backend/\` | FastAPI 后端 |
| \`frontend/admin-web/dist\` | 管理后台静态产物 |
| \`frontend/portal-web/dist\` | 用户中心静态产物 |
| \`deploy/baota/\` | 宝塔伪静态 + API 片段 |
| \`scripts/\` | 部署 / 构建 / 备份脚本 |
| \`docs/PACKAGING.md\` | 打包与交付（完整文档） |
| \`docs/INDEX.md\` | 文档索引 |
| \`docs/release/\` | 发版记录 |

完整说明见包内 \`docs/PACKAGING.md\`。

## 快速部署（宝塔）

\`\`\`bash
bash scripts/gen-secrets.sh
# 编辑 .env.prod：CORS_ORIGINS、域名
bash scripts/deploy-baota-static.sh
\`\`\`

宝塔建站：

| 站点 | 根目录 |
|------|--------|
| admin.example.com | \`frontend/admin-web/dist\` |
| portal.example.com | \`frontend/portal-web/dist\` |

每个站点：伪静态见 \`deploy/baota/rewrite-*.conf\`，API 见 \`server-snippet-*-api.conf\`。

默认账号：\`admin@cenkor.cn\` / \`admin123\`
EOF

ARCHIVE="$RELEASE_DIR/${PKG_NAME}.tar.gz"
info "压缩 ${ARCHIVE} ..."
tar -czf "$ARCHIVE" -C "$STAGE" "$PKG_NAME"

rm -rf "$STAGE"

SIZE="$(du -h "$ARCHIVE" | cut -f1)"
info "完成：${ARCHIVE} (${SIZE})"
echo ""
echo "  解压：tar -xzf ${PKG_NAME}.tar.gz"
echo "  文档：docs/PACKAGING.md · docs/INDEX.md"
