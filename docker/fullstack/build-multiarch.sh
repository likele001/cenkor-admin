#!/bin/bash
# Cenkor Admin · 全栈镜像多架构构建（linux/amd64 + linux/arm64）
# 用法：bash docker/fullstack/build-multiarch.sh [--push]
# 说明：ARM64 交叉构建首次需启用 binfmt；--push 推送到 registry（去掉 --load）
set -euo pipefail
cd "$(dirname "$0")/../.."
PUSH="${1:-}"
PUSH_FLAG=""; [ "$PUSH" = "--push" ] && PUSH_FLAG="--push" || PUSH_FLAG="--load"
PLAT="linux/amd64,linux/arm64"

# 版本单一来源：VERSION 文件；REGISTRY 可选前缀（如 registry.cenkor.cn/cenkor）
VERSION="$( { [ -f backend/src/cenkor_admin/VERSION ] && tr -d ' \n' < backend/src/cenkor_admin/VERSION; } 2>/dev/null || echo 0.1.0)"
[ -n "$VERSION" ] || VERSION="0.1.0"
REG="${REGISTRY:-}"
[ -n "$REG" ] && REG="${REG%/}/"
tag() { # $1=本地名 → 输出 -t 参数
  echo "-t ${REG}$1:latest -t ${REG}$1:${VERSION}"
}
echo "[cenkor] 版本 ${VERSION}  registry='${REG:-<本地>}'  push=${PUSH:-<load>}"

docker buildx create --name cenkor-multi --use >/dev/null 2>&1 || docker buildx use cenkor-multi

echo "[cenkor] 构建后端 ..."
docker buildx build --platform "$PLAT" \
  -f docker/fullstack/backend.Dockerfile $(tag cenkor-admin-backend) $PUSH_FLAG .

echo "[cenkor] 构建前端 admin / portal / developer ..."
declare -A img=(
  [admin-web]=cenkor-admin-web-admin
  [portal-web]=cenkor-admin-web-portal
  [developer-web]=cenkor-admin-web-developer
)
for fe in admin-web portal-web developer-web; do
  docker buildx build --platform "$PLAT" \
    -f docker/fullstack/frontend.Dockerfile --build-arg FRONTEND="$fe" \
    $(tag "${img[$fe]}") $PUSH_FLAG .
done

echo "[cenkor] 完成。镜像已打 :latest 与 :${VERSION} 标签"