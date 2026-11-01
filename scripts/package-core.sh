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
    --exclude='.env.*' \
    --exclude='*.bak' \
    --exclude='*.bak-*' \
    --exclude='*.bak.*' \
    --exclude='_bak-*' \
    --exclude='_rollback_bak_*' \
    --exclude='.stale-apps' \
    --exclude='.mimocode' \
    --exclude='*.log' \
    --exclude='*.log.[0-9]*' \
    --exclude='logs' \
    --exclude='*.orig' \
    --exclude='*.rej' \
    --exclude='./release' \
    --exclude='./www' \
    --exclude='verify_v11.py' \
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

# ---- 闭源迁移接力：erp/crm/mes 整段排除后，commerce 首个迁移的父节点会悬空 ----
# alembic/versions/commerce/20260922_0020_commerce.py 原本 down_revision = 20260904_mes_0009。
# 它只新建 app_pricing / app_orders / app_licenses / app_license_bindings 四张自建表，
# 不引用 MES/ERP/CRM 的任何表或 schema，因此置空父节点、让它成为独立分支起点是安全的。
# 不改仓库源码，只改包内副本：交付包必须能直接 `alembic upgrade head`。
COMMERCE_SEED="$DEST/backend/alembic/versions/commerce/20260922_0020_commerce.py"
if [ -f "$COMMERCE_SEED" ]; then
  sed -i 's|^down_revision = "20260904_mes_0009"$|down_revision = None  # 核心包：原父 20260904_mes_0009 属闭源 MES 段，本迁移不依赖其表|' "$COMMERCE_SEED"
  if ! grep -q '^down_revision = None' "$COMMERCE_SEED"; then
    echo "" >&2
    echo "✗ 打包中止：commerce 迁移父节点改接失败（20260922_0020_commerce.py 已变化）" >&2
    echo "  闭源段被排除后该迁移会指向不存在的 revision，交付包将无法执行 alembic upgrade。" >&2
    echo "  请检查 scripts/package-core.sh 里的 COMMERCE_SEED 处理逻辑。" >&2
    rm -rf "$STAGE"
    exit 1
  fi
  info "已重接 commerce 迁移父节点（原 20260904_mes_0009 属闭源段，无表依赖）"
fi

# .env.* 被整体排除（含 .env.bak-* 这类带真实凭据的历史备份），只补回模板
for tpl in .env.example backend/.env.example; do
  [ -f "$ROOT/$tpl" ] && install -D -m644 "$ROOT/$tpl" "$DEST/$tpl"
done

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

## 迁移说明

核心包**不含** ERP / CRM / MES 商业模块，对应迁移目录（\`alembic/versions/erp\`、\`crm\`、\`mes\`）
已从包中排除。\`commerce\` 的首个迁移原本接在闭源 MES 迁移之后，包内已把它的父节点置空
（该迁移只新建自身 4 张表，不依赖商业模块的任何表），因此可直接执行：

\`\`\`bash
cd backend && alembic upgrade head
\`\`\`

若未来要接入商业模块，请使用完整仓库的迁移目录，不要沿用本包内的迁移链。

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
FORBIDDEN_PATTERNS='backend/src/cenkor_admin/apps/(erp|crm|mes|workflow|payment)/|backend/src/apps/|frontend/developer-web/|backend/src/cenkor_admin/static/apps/(erp|crm|mes|workflow|payment)/|backend/alembic/versions/(erp|crm|mes)/|verify_v11\.py'
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

# ---- 交付前自检之二：不许出现凭据文件 ----
# .env.bak-20261007 这类历史备份带真实密钥，且从未进过 git（.gitignore 管不到它们的
# 兄弟文件名），tar 会照单全收。凡 .env 变体（example 除外）、私钥、*.bak 一律拦截。
SECRET_HITS="$(tar -tzf "$ARCHIVE" 2>/dev/null \
  | grep -E '(^|/)\.env(\..*)?$|\.pem$|\.key$|(^|/)id_(rsa|ed25519)|\.bak(-[^/]*)?$' \
  | grep -vE '(^|/)\.env\.example$' | head -20 || true)"
if [ -n "$SECRET_HITS" ]; then
  echo "" >&2
  echo "✗ 打包中止：检测到凭据 / 备份文件被打进核心包" >&2
  echo "  前几项：" >&2
  printf '%s\n' "$SECRET_HITS" | sed 's/^/    /' >&2
  echo "" >&2
  echo "  真实 .env 与私钥不得随包交付（.env.example 模板除外）。" >&2
  echo "  请在 scripts/package-core.sh 的 --exclude 列表里补齐后重试。" >&2
  rm -rf "$STAGE" "$ARCHIVE"
  exit 1
fi
info "自检通过：包内无凭据 / 备份文件（.env 变体仅保留 .env.example）"

# ---- 交付前自检之三：不许出现运行时垃圾（日志 / 数据库备份 / 旧产物） ----
# backend/logs/hub.log（5M+ 生产日志）、_rollback_bak_*/cenkor_db.sql（全量库备份）、
# backend/.stale-apps/（已卸载应用的残留，含闭源 payment 产物）都曾被打进包。
# 这些都是 untracked 文件，.gitignore 管不到，只能靠这里拦。
GARBAGE_PATTERNS='(^|/)logs?/|\.log$|\.log\.[0-9]+$|(^|/)_bak-|(^|/)_rollback_bak_|(^|/)_work/|\.bak\.|(^|/)\.stale-apps/|(^|/)\.mimocode/|(^|/)www/wwwroot/'
GARBAGE="$(tar -tzf "$ARCHIVE" 2>/dev/null | grep -E "$GARBAGE_PATTERNS" | head -20 || true)"
if [ -n "$GARBAGE" ]; then
  echo "" >&2
  echo "✗ 打包中止：检测到运行时垃圾被打进核心包（共 $(tar -tzf "$ARCHIVE" | grep -cE "$GARBAGE_PATTERNS") 项）" >&2
  echo "  前几项：" >&2
  printf '%s\n' "$GARBAGE" | sed 's/^/    /' >&2
  echo "" >&2
  echo "  日志、数据库备份、旧产物、已卸载应用残留不得随包交付。" >&2
  echo "  请在 scripts/package-core.sh 的 --exclude 列表里补齐后重试。" >&2
  rm -rf "$STAGE" "$ARCHIVE"
  exit 1
fi
info "自检通过：包内无运行时垃圾（日志 / 库备份 / 旧产物 / stale-apps）"

# ---- 交付前自检之四：关键文件必须在（防止 --exclude 写过头把包打空） ----
# 用纯 bash 内建匹配，不走 `printf | grep -q`：grep -q 命中即退出会让 printf 吃到
# SIGPIPE，配合 set -o pipefail 会被误判成「文件缺失」，且失败项随缓冲区时机漂移。
MISSING=""
PKG_LIST="$(tar -tzf "$ARCHIVE")"
HAYSTACK=$'\n'"$PKG_LIST"$'\n'
for req in \
  PACKAGE.md README.md LICENSE \
  backend/src/cenkor_admin/main.py \
  backend/src/cenkor_admin/VERSION \
  backend/alembic.ini \
  backend/.env.example \
  frontend/admin-web/dist/index.html \
  frontend/portal-web/dist/index.html \
  frontend/landing/index.html ; do
  case "$HAYSTACK" in
    *$'\n'"$PKG_NAME/$req"$'\n'*) ;;
    *) MISSING="$MISSING $req" ;;
  esac
done
if [ -n "$MISSING" ]; then
  echo "" >&2
  echo "✗ 打包中止：核心包缺少关键文件：$MISSING" >&2
  echo "  多半是 --exclude 写得过宽，或对应构建产物尚未生成（先跑 scripts/build-frontends.sh）。" >&2
  rm -rf "$STAGE" "$ARCHIVE"
  exit 1
fi
info "自检通过：关键文件齐全（后端入口 / 迁移 / 三套前端产物 / 环境模板）"

# ---- 交付前自检之五：包内迁移链必须自洽（每个 down_revision 都要在包内） ----
# 排除闭源迁移目录最容易留下的坑：公开迁移指向被删掉的父节点，包能打出来，
# 但用户一跑 alembic upgrade head 就 KeyError。这里静态解析一遍再放行。
if command -v python3 >/dev/null 2>&1; then
  MIG_BAD="$(python3 - "$DEST" <<'PYCHECK'
import ast, sys
from pathlib import Path

root = Path(sys.argv[1]) / "backend/alembic/versions"
revs, downs, bad, files = set(), {}, [], 0
for f in sorted(root.rglob("*.py")):
    if "__pycache__" in f.parts or f.name in ("__init__.py",):
        continue
    files += 1
    try:
        tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError as e:
        bad.append(f"{f.name}: 语法错误 {e}")
        continue
    got = {}
    for node in tree.body:
        tgt = None
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if len(names) == 1:
                tgt = names[0]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            tgt = node.target.id
        if tgt in ("revision", "down_revision") and node.value is not None:
            try:
                got[tgt] = ast.literal_eval(node.value)
            except Exception:
                pass
    rev = got.get("revision")
    if not rev:
        bad.append(f"{f.name}: 缺少 revision")
        continue
    revs.add(rev)
    d = got.get("down_revision")
    if isinstance(d, str):
        d = [d]
    downs[rev] = [x for x in (d or []) if x]

for rev, ps in sorted(downs.items()):
    for p in ps:
        if p not in revs:
            bad.append(f"{rev} 的父节点 {p} 不在包内")

if not files:
    bad.append("包内一个迁移文件都没有")
print("\n".join(bad))
PYCHECK
)"
  if [ -n "$MIG_BAD" ]; then
    echo "" >&2
    echo "✗ 打包中止：核心包迁移链不完整（alembic upgrade head 会失败）" >&2
    printf '%s\n' "$MIG_BAD" | sed 's/^/    /' >&2
    echo "" >&2
    echo "  多半是排除了某个迁移目录，但公开迁移仍指向它的 revision。" >&2
    echo "  请在 scripts/package-core.sh 里为该迁移补「父节点重接」逻辑。" >&2
    rm -rf "$STAGE" "$ARCHIVE"
    exit 1
  fi
  info "自检通过：包内迁移链自洽（父 revision 齐全，可直接 alembic upgrade head）"
else
  warn "跳过迁移链自检（当前环境没有 python3）"
fi

rm -rf "$STAGE"

SIZE="$(du -h "$ARCHIVE" | cut -f1)"
info "完成：${ARCHIVE} (${SIZE})"
echo ""
echo "  解压：tar -xzf ${PKG_NAME}.tar.gz"
echo "  文档：docs/packaging.md · docs/index.md"
