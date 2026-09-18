#!/bin/bash
# Cenkor Admin · 全栈镜像离线导出（内网/无外网部署）
# 用法：bash docker/fullstack/export-fullstack.sh [输出目录]
# 产物：<out>/cenkor-fullstack_<时间戳>.tar.gz（含全部自有镜像 + postgres/redis/minio）
set -euo pipefail
cd "$(dirname "$0")/../.."

OUT_DIR="${1:-dist-fullstack-images}"
mkdir -p "$OUT_DIR"
stamp="$(date +%Y%m%d_%H%M%S)"
archive="${OUT_DIR}/cenkor-fullstack_${stamp}.tar.gz"

images=(
  cenkor-admin-backend:fullstack
  cenkor-admin-web-admin:fullstack
  cenkor-admin-web-portal:fullstack
  cenkor-admin-web-developer:fullstack
  postgres:16-alpine
  redis:7-alpine
  minio/minio:latest
)

echo "[cenkor] 导出 ${#images[@]} 个镜像 → ${archive} ..."
# 提示先确保 compose 已 build
docker save "${images[@]}" | gzip -9 > "${archive}"
echo "[cenkor] 完成: ${archive} ($(du -h "${archive}" | cut -f1))"
echo
echo "目标机（无外网）导入并启动："
echo "  docker load < ${archive}"
echo "  docker compose -f docker-compose.fullstack.yml --env-file .env.fullstack up -d   # 无需再联网拉取/构建"