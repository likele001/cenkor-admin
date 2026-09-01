#!/bin/bash
# ERP App · 本地安装（路径 A：内置调试）
#
# 把整个 apps/erp/ 目录软链到 cenkor-admin 的内置 apps 位置，
# 配合 manifest 自动扫描机制，重启后端即可在 AppsView 看到。
#
# 用法:
#   bash scripts/install.sh        # 软链模式（开发用）
#   bash scripts/install.sh copy   # 复制模式（生产用）
#
set -euo pipefail

MODE="${1:-symlink}"
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_KEY="$(basename "$APP_DIR")"

CENKOR_ADMIN="/www/wwwroot/cenkor-admin"
TARGET_DIR="$CENKOR_ADMIN/backend/src/cenkor_admin/apps/$APP_KEY"

if [ ! -d "$CENKOR_ADMIN" ]; then
  echo "[install] CENKOR_ADMIN 未找到: $CENKOR_ADMIN"
  exit 1
fi

if [ -e "$TARGET_DIR" ]; then
  echo "[install] 目标已存在: $TARGET_DIR"
  echo "[install] 如需覆盖请先删除: rm -rf $TARGET_DIR"
  exit 0
fi

case "$MODE" in
  symlink)
    ln -s "$APP_DIR" "$TARGET_DIR"
    echo "[install] symlink: $TARGET_DIR -> $APP_DIR"
    ;;
  copy)
    cp -r "$APP_DIR" "$TARGET_DIR"
    echo "[install] copied: $TARGET_DIR"
    ;;
  *)
    echo "[install] 未知模式: $MODE (仅支持 symlink / copy)"
    exit 2
    ;;
esac

echo "[install] 下一步："
echo "  1) 重启 cenkor-admin 后端 (docker compose restart backend 或 systemctl restart cenkor-backend)"
echo "  2) 登录后台 → 应用中心 → 应能看到 '$APP_KEY' App"
echo "  3) 点击安装 → 自动建表 + 加权限 + 加菜单"