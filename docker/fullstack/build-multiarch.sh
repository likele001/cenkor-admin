#!/bin/bash
# Cenkor Admin · 全栈镜像多架构构建（linux/amd64 + linux/arm64）
# 用法：bash docker/fullstack/build-multiarch.sh [--push]
# 说明：ARM64 交叉构建首次需启用 binfmt；--push 推送到 registry（去掉 --load）
set -euo pipefail
cd "$(dirname "$0")/../.."
PUSH="${1:-}"
PUSH_FLAG=""; [ "$PUSH" = "--push" ] && PUSH_FLAG="--push" || PUSH_FLAG="--load"
PLAT="linux/amd64,linux/arm64"

docker buildx create --name cenkor-multi --use >/dev/null 2>&1 || docker buildx use cenkor-multi

echo "[cenkor] 构建后端 ..."
docker buildx build --platform "$PLAT" \
  -f docker/fullstack/backend.Dockerfile -t cenkor-admin-backend:fullstack-multi $PUSH_FLAG .

echo "[cenkor] 构建前端 admin / portal / developer ..."
declare -A img=(
  [admin-web]=cenkor-admin-web-admin
  [portal-web]=cenkor-admin-web-portal
  [developer-web]=cenkor-admin-web-developer
)
for fe in admin-web portal-web developer-web; do
  docker buildx build --platform "$PLAT" \
    -f docker/fullstack/frontend.Dockerfile --build-arg FRONTEND="$fe" \
    -t "${img[$fe]}:fullstack-multi" $PUSH_FLAG .
done

echo "[cenkor] 完成。使用多架构镜像：把 compose 中 image 后缀 :fullstack 改为 :fullstack-multi"