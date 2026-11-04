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

# ---- 构建产物回填索引：frontend/landing（nginx 线上目录） ----
# frontend/landing/ 是 git 跟踪的，构建用 rsync --delete 换掉 assets/ 里的哈希
# 文件。依赖升级（v0.5.15 的 vite 5 → 6）会让哈希全变：旧文件被删、新文件未跟踪。
# 不处理的话下面「跟踪文件被删除」会直接中止（v0.5.0/0.5.1/0.5.2 同因失败），
# 而 `git ls-files | tar` 也拿不到新哈希资源，包里的落地页会 404。
# 这里把构建结果同步进索引，让 ls-files 反映真实磁盘内容；打包结束再还原。
git add -A -- frontend/landing >/dev/null 2>&1 || true

# ---- 前置检查：git 跟踪但磁盘上不存在的文件 ----
# `git ls-files | tar` 的前提是「跟踪的文件都在工作区」。一旦有文件被构建脚本
# 误删（历史上就是 `rsync --delete` 删 landing/ 里的手写资产），tar 只会抛出
# 一串 `Cannot stat`，真正的起因（谁删的）看不出来，排查成本极高。
# 这里先查一遍 `git status` 的已删除项，直接指明原因与恢复方式。
DELETED_TRACKED="$(git status --porcelain --untracked-files=no 2>/dev/null | grep '^ D' | sed 's/^ D //' | head -20 || true)"
if [ -n "$DELETED_TRACKED" ]; then
  echo "" >&2
  echo "✗ 打包中止：有 git 跟踪的文件在工作区里被删除，无法进包" >&2
  printf '%s\n' "$DELETED_TRACKED" | sed 's/^/    /' >&2
  echo "" >&2
  echo "  常见原因：scripts/build-frontends.sh 的 rsync --delete 清掉了 frontend/landing/" >&2
  echo "  里不参与构建的资产（旧静态页 / docs-content / robots.txt 等）。" >&2
  echo "" >&2
  echo "  恢复：git checkout -- <上面列出的路径>" >&2
  echo "  长期：确认 build-frontends.sh 的 rsync 排除清单已包含这些手写资产。" >&2
  exit 1
fi

info "复制核心文件到临时目录..."
# ── 以 git 跟踪清单为源，不再靠 --exclude 逐条追赶 ──────────────────────────
# tar 读文件系统、不读 .gitignore。过去四轮泄漏全部是同一原因：
#   ① 闭源应用目录（erp/crm/mes/workflow）
#   ② .env.bak-*、backend/logs/hub.log(5.2M)、_rollback_bak_*/cenkor_db.sql(1.7M)
#   ③ ext 混合目录里的闭源迁移（workflow 流程定义等）
#   ④ deploy/baota/cenkor-backend.host.env（真实 SECRET_KEY + 数据库口令）
# 这些东西 .gitignore 里都登记了，但 tar 不认识。改成以 `git ls-files` 为源后，
# gitignore 自动生效，新增闭源资产不必再改本脚本。
# 下面只保留「已进 git 但不该交付」的少量例外。
TRACKED_TAR="$STAGE/.payload-tracked.tar"
(
  cd "$ROOT"
  git ls-files -z \
    | grep -zvE '^(frontend/developer-web/|docs/domain_setup\.md|deploy/(addons|website|examples|nginx/snippets)/|docs/addons/|docker-compose\.addon-website\.yml$|verify_v11\.py$|docs/05-用户手册/(crm|erp|mes|workflow)_操作手册\.md$|www/wwwroot/|\.mimocode/)|\.bak[^/]*$' \
    | tar --null -T - -cf "$TRACKED_TAR"
)
# 用中转文件而不是直接 `| tar -x`：多个 tar 流串进同一个 tar -x 时，tar -x 读完
# 第一个归档的 EOF 就关 stdin，上游 tar -c 吃 SIGPIPE（141），在 set -o pipefail 下
# 整个脚本静默退出——这是「复制核心文件」后没有任何报错就中断的原因。
tar -xf "$TRACKED_TAR" -C "$DEST"
rm -f "$TRACKED_TAR"

# ── 构建产物被 gitignore，但必须交付 ──────────────────────────────────────
# 三套前端 dist + 开源应用的前端插件产物（闭源应用的插件目录逐个排除，
# payment 自 v0.5.11 起开源，其 plugin.js 随包交付）。
ARTIFACT_TAR="$STAGE/.payload-artifacts.tar"
(
  cd "$ROOT"
  paths=()
  for p in frontend/admin-web/dist frontend/portal-web/dist frontend/landing-web/dist; do
    [ -d "$p" ] && paths+=("$p")
  done
  [ -d backend/src/cenkor_admin/static/apps ] && paths+=("backend/src/cenkor_admin/static/apps")
  if [ "${#paths[@]}" -eq 0 ]; then
    echo "✗ 打包中止：找不到任何前端构建产物（先跑 scripts/build-frontends.sh）" >&2
    exit 1
  fi
  tar -c \
    --exclude='backend/src/cenkor_admin/static/apps/erp' \
    --exclude='backend/src/cenkor_admin/static/apps/crm' \
    --exclude='backend/src/cenkor_admin/static/apps/mes' \
    --exclude='backend/src/cenkor_admin/static/apps/workflow' \
    -f "$ARTIFACT_TAR" "${paths[@]}"
)
tar -xf "$ARTIFACT_TAR" -C "$DEST"
rm -f "$ARTIFACT_TAR"

# ---- 闭源迁移必须一个不剩 ----
# 早先只排除了 alembic/versions/{erp,crm,mes} 三个目录，ext 是「混合目录」：
# 目录里既有平台级公开迁移，也有闭源商业迁移（.gitignore 逐个登记）。
# commerce/ 自 v0.5.11 起整体开源，不再属于混合目录。
# 这里对包内迁移数与 git 跟踪数做精确对账，差一个就中止。
PKG_MIG="$(cd "$DEST" && find backend/alembic/versions -name '*.py' -not -path '*/__pycache__/*' | wc -l)"
GIT_MIG="$(cd "$ROOT" && git ls-files 'backend/alembic/versions' | grep -c '\.py$' || true)"
if [ "$PKG_MIG" -ne "$GIT_MIG" ]; then
  echo "" >&2
  echo "✗ 打包中止：包内迁移 $PKG_MIG 个，git 跟踪 $GIT_MIG 个，数量不符" >&2
  echo "  多出的通常是闭源商业迁移（ext 混合目录里的 workflow 等）。用这条命令定位：" >&2
  echo "    comm -13 <(git ls-files backend/alembic/versions|sort) \\" >&2
  echo "             <(cd 解压目录 && find backend/alembic/versions -name '*.py'|sort)" >&2
  rm -rf "$STAGE"
  exit 1
fi
info "已核对迁移数：包内 $PKG_MIG 个 = git 跟踪 $GIT_MIG 个（闭源迁移未混入）"

# .env.* 被整体排除（含 .env.bak-* 这类带真实凭据的历史备份），只补回模板
for tpl in .env.example backend/.env.example; do
  [ -f "$ROOT/$tpl" ] && install -D -m644 "$ROOT/$tpl" "$DEST/$tpl"
done

info "写入安装说明 PACKAGE.md..."
# 迁移 head 实算，不写死 —— v0.5.3 补迁移后这里的文案曾长期过期，
# 导致每个 Release 包的说明都在告诉用户一个旧 head。
PKG_HEAD="$(cd "$ROOT" && python3 scripts/check-migration-graph.py --tracked-only 2>/dev/null \
  | sed -nE 's/^[[:space:]]*head[[:space:]]*:[[:space:]]*//p' | head -1)"
PKG_HEAD="${PKG_HEAD:-unknown}"
PKG_MIG_COUNT="$(cd "$ROOT" && git ls-files 'backend/alembic/versions' | grep -c '\.py$')"
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

核心包**不含** ERP / CRM / MES / workflow 商业模块，也不含 ext 混合目录里的
闭源商业迁移（定价、订单、授权、支付、市场、分成、促销、云绑定、工作流、应用发布）。
包内迁移与公开仓库完全一致，可直接执行：

\`\`\`bash
cd backend && alembic upgrade head
\`\`\`

迁移链唯一 head 为 \`${PKG_HEAD}\`，共 ${PKG_MIG_COUNT} 个迁移。若未来要接入商业模块，
请使用完整仓库的迁移目录，不要把两套迁移混用。

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
FORBIDDEN_PATTERNS='backend/src/cenkor_admin/apps/(erp|crm|mes|workflow)/|backend/src/apps/|frontend/developer-web/|backend/src/cenkor_admin/static/apps/(erp|crm|mes|workflow)/|backend/alembic/versions/(erp|crm|mes)/|backend/alembic/versions/ext/20260925_0027_workflow|verify_v11\.py'
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
info "自检通过：包内无闭源资产（erp / crm / mes / workflow / src-apps / developer-web）"

# ---- 交付前自检之二：不许出现凭据文件 ----
# .env.bak-20261007 这类历史备份带真实密钥，且从未进过 git（.gitignore 管不到它们的
# 兄弟文件名），tar 会照单全收。凡 .env 变体（example 除外）、私钥、*.bak 一律拦截。
SECRET_HITS="$(tar -tzf "$ARCHIVE" 2>/dev/null \
  | grep -E '(^|/)\.env$|(^|/)\.env\.[^/]*$|\.env$|\.env\.[^/]*$|\.pem$|\.key$|(^|/)id_(rsa|ed25519)|\.bak([-_.][^/]*)?$' \
  | grep -vE '\.env\.example$' | head -20 || true)"
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
# backend/.stale-apps/（已卸载应用的残留产物）都曾被打进包。
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
    echo "  多半是排除了某个迁移，但公开迁移仍指向它的 revision。" >&2
    echo "  先确认该父迁移是否属闭源（.gitignore §155-172）；属闭源则连同引用它的迁移一起核对。" >&2
    rm -rf "$STAGE" "$ARCHIVE"
    exit 1
  fi
  info "自检通过：包内迁移链自洽（父 revision 齐全，可直接 alembic upgrade head）"
else
  warn "跳过迁移链自检（当前环境没有 python3）"
fi

# ---- 提示：包内仍有 git 未跟踪的文件 ----
# 构建产物（dist / 插件产物）与 PACKAGE.md 本就未跟踪，属正常；
# 其余未跟踪文件多为尚未提交的开发内容，会跟着 tar 一起交付出去，需要人工过一眼。
BUILD_ARTIFACTS='^(PACKAGE.md|frontend/(admin-web|portal-web|landing-web)/dist/|frontend/landing/|backend/src/cenkor_admin/static/apps/)'
UNTRACKED="$(comm -23 \
  <(tar -tzf "$ARCHIVE" | sed "s|^$PKG_NAME/||" | grep -v '/$' | sort -u) \
  <(cd "$ROOT" && git -c core.quotePath=false ls-files | sort -u) 2>/dev/null \
  | grep -vE "$BUILD_ARTIFACTS" || true)"
if [ -n "$UNTRACKED" ]; then
  N="$(printf '%s\n' "$UNTRACKED" | wc -l | tr -d ' ')"
  warn "包内有 $N 个文件不在 git 跟踪中，会随包交付，请确认是否合适："
  printf '%s\n' "$UNTRACKED" | head -15 | sed 's/^/    /'
  [ "$N" -gt 15 ] && echo "    …（共 $N 条，仅显示前 15 条）"
  echo "    处理方式：该提交的 git add；不该交付的加 --exclude。"
fi

# 还原索引：产物已进 tar，暂存区不留构建垃圾（本地手工打包时尤其重要）
git reset -q -- frontend/landing >/dev/null 2>&1 || true

rm -rf "$STAGE"

SIZE="$(du -h "$ARCHIVE" | cut -f1)"
info "完成：${ARCHIVE} (${SIZE})"
echo ""
echo "  解压：tar -xzf ${PKG_NAME}.tar.gz"
echo "  文档：docs/packaging.md · docs/index.md"
