#!/bin/bash
# 宝塔 Python 项目启动脚本（cenkor 3.12 虚拟环境）
set -euo pipefail
cd /www/wwwroot/cenkor-admin/backend
export PYTHONPATH=/www/wwwroot/cenkor-admin/backend/src

PYTHON_BIN="${PYTHON_BIN:-/www/server/pyporject_evn/cenkor/bin/python3}"

ENV_FILE=/www/wwwroot/cenkor-admin/deploy/baota/cenkor-backend.host.env
if [ -f "$ENV_FILE" ]; then
  set -a
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ''|\#*) continue ;;
      *=*) export "$line" ;;
    esac
  done < "$ENV_FILE"
  set +a
fi

exec "$PYTHON_BIN" -m uvicorn cenkor_admin.main:app \
  --host 127.0.0.1 \
  --port 8002 \
  --workers 2
