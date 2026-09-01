#!/bin/bash
# ERP App · ZIP 打包脚本（路径 B：商店发布）
#
# 用法:
#   bash scripts/build.sh [version]
#
# 产物: release/erp-{version}.zip
#
# 包结构（参考 dev.cenkor.cn/docs#zip-structure）:
#   erp-{version}.zip
#   ├── __init__.py
#   ├── manifest.py
#   ├── alembic/
#   │   └── versions/
#   │       └── *.py
#   ├── scripts/
#   ├── docs/
#   └── frontend/
#       └── dist/
#           ├── plugin.js
#           └── plugin.css (如有)
#
set -euo pipefail

VERSION="${1:-1.0.0}"
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="$(basename "$APP_DIR")"
OUT_DIR="$APP_DIR/release"
mkdir -p "$OUT_DIR"
OUT_FILE="$OUT_DIR/${APP_NAME}-${VERSION}.zip"

echo "[build] app=$APP_NAME version=$VERSION"

# 1) 前端构建（如已构建会跳过；首次必须构建）
if [ -d "$APP_DIR/frontend" ]; then
  if [ ! -f "$APP_DIR/frontend/dist/plugin.js" ]; then
    echo "[build] building frontend ..."
    cd "$APP_DIR/frontend"
    if [ -f package-lock.json ]; then
      npm ci --silent
    else
      npm install --silent
    fi
    npm run build
    cd "$APP_DIR"
  else
    echo "[build] frontend/dist/plugin.js 已存在，跳过构建"
  fi
fi

# 2) 清理临时文件
rm -f "$OUT_FILE"

# 3) 打包
echo "[build] creating $OUT_FILE ..."
cd "$APP_DIR"

# 强制白名单，避免把 node_modules / .git / __pycache__ 打进去
zip -r "$OUT_FILE" \
  __init__.py \
  manifest.py \
  models/ \
  router.py \
  sp_router.py \
  so_router.py \
  po_router.py \
  fin_router.py \
  gl_router.py \
  wh_router.py \
  mfg_router.py \
  alembic/ \
  scripts/ \
  docs/ \
  frontend/dist/ \
  -x "*/__pycache__/*" "*.pyc" "*/node_modules/*" "*/.git/*" "*/dist/.vite/*"

# 4) 输出信息
SIZE=$(du -h "$OUT_FILE" | cut -f1)
SHA256=$(sha256sum "$OUT_FILE" | cut -d' ' -f1)
echo "[build] done: $OUT_FILE ($SIZE)"
echo "[build] sha256: $SHA256"
echo "[build] 下一步："
echo "  1) 登录 https://dev.cenkor.cn/"
echo "  2) 上传 $OUT_FILE"
echo "  3) 后台审核 → 安装"