#!/bin/bash
# ERP App · 本地开发脚本
#
# 用法:
#   bash scripts/dev.sh backend          # 启后端开发模式（uvicorn reload）
#   bash scripts/dev.sh frontend         # 启前端开发模式（vite）
#   bash scripts/dev.sh migrate          # 执行 alembic 迁移
#   bash scripts/dev.sh rollback         # 回滚最近一次迁移
#   bash scripts/dev.sh clean            # 清 pyc + __pycache__
#   bash scripts/dev.sh test             # 跑 pytest
#
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"

cmd="${1:-help}"

case "$cmd" in
  backend)
    echo "[dev] starting backend with uvicorn --reload ..."
    cd /www/wwwroot/cenkor-admin/backend
    exec uvicorn cenkor_admin.main:app --reload --host 0.0.0.0 --port 8001
    ;;
  frontend)
    echo "[dev] starting frontend dev server ..."
    cd "$APP_DIR/frontend"
    exec npm run dev
    ;;
  migrate)
    echo "[dev] running alembic upgrade head ..."
    cd /www/wwwroot/cenkor-admin/backend
    alembic upgrade head
    ;;
  rollback)
    echo "[dev] rolling back one migration ..."
    cd /www/wwwroot/cenkor-admin/backend
    alembic downgrade -1
    ;;
  clean)
    find "$APP_DIR" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
    find "$APP_DIR" -type f -name '*.pyc' -delete 2>/dev/null || true
    echo "[dev] cleaned"
    ;;
  test)
    echo "[dev] running pytest ..."
    cd /www/wwwroot/cenkor-admin/backend
    pytest apps/erp/tests/ -v
    ;;
  *)
    echo "用法: bash scripts/dev.sh {backend|frontend|migrate|rollback|clean|test}"
    exit 0
    ;;
esac