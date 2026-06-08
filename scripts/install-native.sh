#!/bin/bash
# Cenkor Admin · 裸机 systemd 安装（无 Docker）
set -e
cd "$(dirname "$0")/.."

echo "▸ 安装 Python 依赖..."
cd backend
pip3 install -e . 2>/dev/null || pip3 install -r <(python3 -c "
import tomllib, pathlib
d = tomllib.loads(pathlib.Path('pyproject.toml').read_text())
print('\n'.join(d['project']['dependencies']))
")

echo "▸ 构建前端..."
cd ../frontend/admin-web && npm ci && npm run build
cd ../portal-web && npm ci && npm run build

echo "▸ 数据库迁移..."
cd ../../backend
PYTHONPATH=src alembic upgrade head
PYTHONPATH=src python3 -m cenkor_admin.scripts.seed || true

echo "▸ 安装 systemd units..."
cp deploy/systemd/*.service /etc/systemd/system/
mkdir -p /etc/cenkor
if [ ! -f /etc/cenkor/env.host.override ]; then
  cp deploy/examples/env.host.override /etc/cenkor/env.host.override
  echo "  请编辑 /etc/cenkor/env.host.override 填入 DATABASE_URL"
fi
systemctl daemon-reload
systemctl enable cenkor-backend cenkor-celery cenkor-admin-web cenkor-portal-web
systemctl restart cenkor-backend cenkor-celery cenkor-admin-web cenkor-portal-web

echo "✓ 裸机部署完成。请在宝塔配置反代到 8002/5174/5175"
