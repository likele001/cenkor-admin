#!/bin/bash
# =============================================================
# Cenkor Admin · 将平台 App 打包为「应用中心」可上传的 ZIP
#   用法: bash scripts/package-app.sh <app_key> [version]
#   version 缺省时自动读取 apps/<app_key>/manifest.py
# 产物: backend/src/cenkor_admin/apps/<app_key>/release/<app_key>-<version>.zip
#   包含 manifest.py / __init__.py / 后端代码 / alembic 迁移 / frontend/dist
#   （排除 node_modules、release、__pycache__、.git）
# 上传: 开发者门户或 POST /api/v1/store/submissions（审核通过后安装）
# =============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

APP_KEY="${1:?用法: bash scripts/package-app.sh <app_key> [version]}"
APP_DIR="backend/src/cenkor_admin/apps/${APP_KEY}"

[ -d "$APP_DIR" ] || { echo "✗ 应用不存在: $APP_DIR"; exit 1; }
[ -f "$APP_DIR/manifest.py" ] || { echo "✗ 缺少 manifest.py: $APP_DIR"; exit 1; }
[ -f "$APP_DIR/__init__.py" ] || { echo "✗ 缺少 __init__.py: $APP_DIR"; exit 1; }

VERSION="${2:-$(python3 - "$APP_DIR/manifest.py" <<'PY'
import re, sys
src = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r'\bversion\s*=\s*["\']([^"\']+)["\']', src)
print(m.group(1) if m else "")
PY
)}"
[ -n "$VERSION" ] || { echo "✗ 无法从 manifest.py 解析 version，请显式传入版本号"; exit 1; }

# 1) 前端构建（package.json 定义了 build 脚本时；已有 dist 也会重建保证一致）
if [ -f "$APP_DIR/frontend/package.json" ] && grep -q '"build"' "$APP_DIR/frontend/package.json"; then
  echo "▸ 构建前端 ${APP_KEY}/frontend → dist ..."
  (cd "$APP_DIR/frontend" && { [ -d node_modules ] || npm install; } && npm run build)
  [ -d "$APP_DIR/frontend/dist" ] || { echo "✗ 前端构建后无 dist 产物"; exit 1; }
fi

# 2) 打包
OUT_DIR="$APP_DIR/release"
mkdir -p "$OUT_DIR"
OUT_ZIP="$OUT_DIR/${APP_KEY}-${VERSION}.zip"
TMP_ZIP="$(mktemp)"
rm -f "$TMP_ZIP"
trap 'rm -f "$TMP_ZIP" "$TMP_ZIP".*' EXIT

echo "▸ 打包 ${APP_KEY} v${VERSION} ..."
(cd "$APP_DIR" && zip -rq "$TMP_ZIP" . \
  -x "frontend/node_modules/*" -x "release/*" -x "*__pycache__*" -x "*.pyc" -x ".git/*")

mv -f "$TMP_ZIP" "$OUT_ZIP"
trap - EXIT

echo "✓ 完成: $OUT_ZIP  ($(du -h "$OUT_ZIP" | cut -f1))"
echo "  上传方式: 开发者门户 / POST /api/v1/store/submissions（先注册开发者，审核通过后安装）"