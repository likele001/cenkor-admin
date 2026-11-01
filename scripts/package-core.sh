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

VERSION_FILE="$ROOT/backend/src/cenkor_admin/VERSION"
# 版本单一来源：PACKAGE_VERSION 覆盖 > VERSION 文件 > 0.1.0
VERSION="${PACKAGE_VERSION:-$( { [ -f "$VERSION_FILE" ] && tr -d ' \n' < "$VERSION_FILE"; } 2>/dev/null || echo 0.1.0)}"
[ -n "$VERSION" ] || VERSION="0.1.0"
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
    --exclude='docs/domain_setup.md' \
    --exclude='backend/src/apps' \
    --exclude='frontend/developer-web' \
    --exclude='backend/src/cenkor_admin/apps/erp' \
    --exclude='backend/src/cenkor_admin/apps/crm' \
    --exclude='backend/src/cenkor_admin/apps/mes' \
    --exclude='backend/src/cenkor_admin/apps/workflow' \
    --exclude='backend/src/cenkor_admin/apps/payment' \
    --exclude='backend/src/cenkor_admin/static/apps/erp' \
    --exclude='backend/src/cenkor_admin/static/apps/crm' \
    --exclude='backend/src/cenkor_admin/static/apps/mes' \
    --exclude='backend/src/cenkor_admin/static/apps/workflow' \
    --exclude='backend/src/cenkor_admin/static/apps/payment' \
    --exclude='backend/src/cenkor_admin/apps/*/release' \
    --exclude='backend/alembic/versions/erp' \
    --exclude='backend/alembic/versions/crm' \
    --exclude='backend/alembic/versions/mes' \
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
| \`docs/packaging.md\` | 打包与交付（完整文档） |
| \`docs/index.md\` | 文档索引 |
| \`docs/release/\` | 发版记录 |

完整说明见包内 \`docs/packaging.md\`。

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

管理员账号：\`admin@cenkor.cn\`（**无默认口令**，初始口令随机生成、只打印一次；忘记可执行 \`bash scripts/reset-admin-password.sh\` 重置）
EOF

ARCHIVE="$RELEASE_DIR/${PKG_NAME}.tar.gz"
info "压缩 ${ARCHIVE} ..."
tar -czf "$ARCHIVE" -C "$STAGE" "$PKG_NAME"

# ---- 交付前自检：包里不许出现闭源商业资产（失败即中止，删产物） ----
# tar 读的是文件系统，不看 .gitignore；闭源应用在本机物理存在，仅靠上面的
# --exclude 列表容易漏（新增一个商业应用就会漏一次）。这里用「特征路径扫描」兜底，
# 宁可让打包失败，也不能产出带着 ERP/CRM/MES 源码的交付包。
FORBIDDEN_PATTERNS='backend/src/cenkor_admin/apps/(erp|crm|mes|workflow|payment)/|backend/src/apps/|frontend/developer-web/|backend/src/cenkor_admin/static/apps/(erp|crm|mes|workflow|payment)/|backend/alembic/versions/(erp|crm|mes)/'
LEAKED="$(tar -tzf "$ARCHIVE" 2>/dev/null | grep -E "$FORBIDDEN_PATTERNS" | head -20 || true)"
if [ -n "$LEAKED" ]; then
  echo "" >&2
  echo "✗ 打包中止：检测到闭源商业资产被打进核心包（共 $(tar -tzf "$ARCHIVE" | grep -cE "$FORBIDDEN_PATTERNS") 项）" >&2
  echo "  前几项：" >&2
  printf '%s\n' "$LEAKED" | sed 's/^/    /' >&2
  echo "" >&2
  echo "  这些目录由 .gitignore 排除（见 docs/migrations.md §13、docs/database-migrations.md §7），" >&2
  echo "  属于商业实现，不能随核心包交付。请在 scripts/package-core.sh 的 --exclude 列表里补齐后重试。" >&2
  rm -rf "$STAGE" "$ARCHIVE"
  exit 1
fi
info "自检通过：包内无闭源资产（erp / crm / mes / workflow / payment / src-apps / developer-web）"

rm -rf "$STAGE"

SIZE="$(du -h "$ARCHIVE" | cut -f1)"
info "完成：${ARCHIVE} (${SIZE})"
echo ""
echo "  解压：tar -xzf ${PKG_NAME}.tar.gz"
echo "  文档：docs/packaging.md · docs/index.md"
