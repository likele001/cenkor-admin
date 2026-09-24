#!/bin/bash
# =============================================================
# Cenkor Admin · 核心平台一键升级（裸机 / 宝塔 venv 部署）
#
# 三种取新代码方式：
#   bash scripts/upgrade.sh --git                 # 从开源仓库 git pull
#   bash scripts/upgrade.sh --tar <核心包.tar.gz>  # 用发版核心包覆盖
#   bash scripts/upgrade.sh --url <下载地址>        # 先下载核心包再覆盖
#
# 可选参数：
#   --skip-backup   跳过数据库备份（不建议）
#   --python <路径>  指定 venv python（默认自动探测 cenkor venv / python3）
#
# Docker 部署请勿用本脚本，改用：
#   docker compose -f docker-compose.baota.yml pull && \
#   docker compose -f docker-compose.baota.yml up -d   （启动会自动 alembic upgrade head）
# =============================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${GREEN}▸${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
die()  { echo -e "${RED}✗${NC} $1" >&2; exit 1; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODE=""; TAR=""; URL=""; SKIP_BACKUP=false; PYBIN=""
while [ $# -gt 0 ]; do
  case "$1" in
    --git) MODE="git" ;;
    --tar) MODE="tar"; TAR="${2:-}"; shift ;;
    --url) MODE="url"; URL="${2:-}"; shift ;;
    --skip-backup) SKIP_BACKUP=true ;;
    --python) PYBIN="${2:-}"; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) die "未知参数：$1（用 --help 查看用法）" ;;
  esac
  shift
done
[ -n "$MODE" ] || die "必须指定升级方式：--git / --tar <file> / --url <url>"

ENV_FILE=".env.prod"; [ -f "$ENV_FILE" ] || ENV_FILE=".env"
env_val() { [ -f "$ENV_FILE" ] && grep -E "^${1}=" "$ENV_FILE" | head -1 | cut -d= -f2- | sed 's/\r$//' || true; }

# 探测 venv python
if [ -z "$PYBIN" ]; then
  for c in /www/server/pyporject_evn/cenkor/bin/python3 "$(command -v python3 || true)"; do
    [ -x "$c" ] && { PYBIN="$c"; break; }; done
fi
[ -n "$PYBIN" ] || die "未找到可用的 python3，请用 --python 指定"
info "使用 Python：$PYBIN"

BACKUP_DIR="${BACKUP_DIR:-/www/backup/cenkor-admin}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OLD_VERSION="$( { [ -f backend/src/cenkor_admin/VERSION ] && cat backend/src/cenkor_admin/VERSION; } 2>/dev/null || echo unknown )"
info "当前版本：$OLD_VERSION"

# ---------- 1. 备份数据库 ----------
if [ "$SKIP_BACKUP" = true ]; then
  warn "已跳过数据库备份"
else
  mkdir -p "$BACKUP_DIR"
  DB_USER="$(env_val POSTGRES_USER)"; DB_USER="${DB_USER:-cenkor}"
  DB_NAME="$(env_val POSTGRES_DB)";   DB_NAME="${DB_NAME:-cenkor}"
  DB_PASS="$(env_val POSTGRES_PASSWORD)"
  DB_PORT="$(env_val DB_HOST_PORT)";  DB_PORT="${DB_PORT:-5433}"
  info "备份 PostgreSQL → $BACKUP_DIR/pg_${STAMP}.sql.gz"
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^cenkor-postgres$'; then
    docker exec -i cenkor-postgres pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_DIR/pg_${STAMP}.sql.gz" \
      || warn "docker pg_dump 失败，尝试直连…"
  fi
  [ -s "$BACKUP_DIR/pg_${STAMP}.sql.gz" ] || \
    PGPASSWORD="$DB_PASS" pg_dump -h 127.0.0.1 -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_DIR/pg_${STAMP}.sql.gz" \
      || warn "数据库备份未成功（若确认无需备份可忽略，或加 --skip-backup）"
fi

# ---------- 2. 取新代码 ----------
if [ "$MODE" = "git" ]; then
  [ -d .git ] || die "当前目录不是 git 仓库，无法 --git 升级"
  if ! git diff --quiet || ! git diff --cached --quiet; then
    warn "工作区有未提交改动，git pull 可能冲突；建议先提交或改用 --tar"
  fi
  info "git fetch + pull（fast-forward）…"
  git fetch --all --tags
  git pull --ff-only || die "git pull 失败（有本地改动或分叉），请手动处理后重试"
else
  [ "$MODE" = "tar" ] && SRC="$TAR" || SRC=""
  if [ "$MODE" = "url" ]; then
    SRC="/tmp/cenkor-core-${STAMP}.tar.gz"
    info "下载核心包 → $SRC"
    curl -fL --retry 3 -o "$SRC" "$URL" || die "下载失败：$URL"
  fi
  [ -n "$SRC" ] && [ -f "$SRC" ] || die "核心包不存在：${SRC:-<空>}"
  STAGE="$(mktemp -d)"
  info "解压核心包到 $STAGE …"
  tar -xzf "$SRC" -C "$STAGE"
  # 核心包顶层是 cenkor-admin-core-<ver>-<date>/，自动定位
  PKGROOT="$(find "$STAGE" -maxdepth 1 -mindepth 1 -type d | head -1)"
  [ -n "$PKGROOT" ] && [ -d "$PKGROOT/backend" ] || die "核心包结构异常（未找到 backend/）"
  info "覆盖代码（保留 .env / uploads / logs / 前端 node_modules）…"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude='.env' --exclude='.env.prod' --exclude='.env.local' \
      --exclude='backend/.env' --exclude='backend/.env.prod' \
      --exclude='backend/src/uploads' --exclude='backend/logs' \
      --exclude='node_modules' --exclude='__pycache__' \
      "$PKGROOT/" "$ROOT/"
  else
    # 无 rsync 时逐目录覆盖（不删除，避免误伤本地数据）
    for d in backend/src backend/alembic backend/alembic.ini frontend scripts deploy docker docs; do
      [ -e "$PKGROOT/$d" ] && cp -a "$PKGROOT/$d" "$ROOT/$(dirname "$d")/" || true
    done
  fi
  rm -rf "$STAGE"
fi

NEW_VERSION="$( { [ -f backend/src/cenkor_admin/VERSION ] && cat backend/src/cenkor_admin/VERSION; } 2>/dev/null || echo unknown )"
info "新版本：$NEW_VERSION"

# ---------- 3. 安装 / 更新 Python 依赖 ----------
info "pip install -r backend/requirements.txt …"
( cd backend && "$PYBIN" -m pip install --disable-pip-version-check -q -r requirements.txt ) \
  || warn "依赖安装报错，若为已满足依赖可忽略"

# ---------- 4. 数据库迁移（启动也会自动跑，这里提前跑以便暴露错误）----------
info "alembic upgrade head …"
( cd backend && PYTHONPATH=src "$PYBIN" -m alembic upgrade head ) \
  || die "迁移失败！数据库可能需回滚：$BACKUP_DIR/pg_${STAMP}.sql.gz"

# ---------- 5. 重启后端 ----------
if [ -x scripts/restart-backend-host.sh ]; then
  info "重启后端（uvicorn）…"
  bash scripts/restart-backend-host.sh
else
  warn "未找到 scripts/restart-backend-host.sh，请手动重启后端进程"
fi

# ---------- 6. 健康检查 ----------
PORT="${BACKEND_HOST_PORT:-8002}"
info "健康检查 http://127.0.0.1:${PORT}/api/health …"
sleep 2
if curl -sf "http://127.0.0.1:${PORT}/api/health" >/dev/null; then
  echo -e "${GREEN}✓ 升级完成：${OLD_VERSION} → ${NEW_VERSION}${NC}"
  echo "  备份：$BACKUP_DIR/pg_${STAMP}.sql.gz"
  echo "  回滚：恢复备份后用旧核心包 --tar 重装并重启"
else
  die "健康检查失败！请查看后端日志确认，必要时回滚备份"
fi
