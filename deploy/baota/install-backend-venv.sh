#!/bin/bash
# 在新 Python 虚拟环境（如宝塔 cenkor 3.12）中安装 backend 依赖
set -euo pipefail
cd "$(dirname "$0")/../../backend"

PY="${1:-/www/server/pyporject_evn/cenkor/bin/python3}"
PIP="${PY%python3*}pip3"
[ -x "$PIP" ] || PIP="${PY%python*}pip3"

echo "▸ Python: $("$PY" --version)"
echo "▸ pip install -r requirements.txt"
"$PIP" install -r requirements.txt
echo "▸ pip install -e ."
"$PIP" install -e .
echo "▸ verify import"
"$PY" -c "import cenkor_admin.main; print('✓ cenkor_admin OK')"
