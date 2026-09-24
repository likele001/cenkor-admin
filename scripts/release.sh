#!/bin/bash
# =============================================================
# Cenkor Admin · 核心发版助手（维护者本地执行）
#
# 作用：统一改写版本单一来源 VERSION 文件 + 中心端 release.json，
#       保证「代码版本」「对外声明的最新版本」不再漂移。
#
# 用法：
#   bash scripts/release.sh 0.2.0
#   bash scripts/release.sh 0.2.0 --notes "修复商店空数据；新增升级检查"
#   bash scripts/release.sh patch        # 自动 +补丁位（0.1.0 → 0.1.1）
#   bash scripts/release.sh minor        # 自动 +次版本（0.1.0 → 0.2.0）
# =============================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}▸${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
VF="backend/src/cenkor_admin/VERSION"
RJ="backend/src/cenkor_admin/release.json"
CUR="$(tr -d ' \n' < "$VF" 2>/dev/null || echo 0.0.0)"

TARGET="${1:-}"; [ -n "$TARGET" ] || { echo "用法: bash scripts/release.sh <版本|patch|minor> [--notes \"...\"]"; exit 1; }
shift || true
NOTES=""
while [ $# -gt 0 ]; do case "$1" in --notes) NOTES="${2:-}"; shift ;; esac; shift; done

# patch/minor 自动递增
bump() {
  local mode="$1" IFS='.'; set -- $CUR
  case "$mode" in
    patch) echo "$1.$2.$(( ${3%%-*} + 1 ))" ;;
    minor) echo "$1.$(( $2 + 1 )).0" ;;
    major) echo "$(( $1 + 1 )).0.0" ;;
  esac
}
case "$TARGET" in
  patch|minor|major) NEW="$(bump "$TARGET")" ;;
  *) NEW="$TARGET" ;;
esac

# 简单 semver 校验
echo "$NEW" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || { warn "版本号格式应为 x.y.z（当前：$NEW）"; exit 1; }
[ "$NEW" = "$CUR" ] && { warn "版本未变化（$CUR）"; exit 0; }

info "版本 bump：$CUR → $NEW"
printf '%s\n' "$NEW" > "$VF"

TODAY="$(date +%Y-%m-%d)"
if [ -f "$RJ" ]; then
  python3 - "$RJ" "$NEW" "$TODAY" "$NOTES" <<'PY'
import json, sys
p, ver, day, notes = sys.argv[1:5]
d = json.load(open(p, encoding="utf-8"))
d["version"] = ver
d["released_at"] = day
if notes:
    d["notes"] = notes
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("release.json 已更新：version=%s released_at=%s" % (ver, day))
PY
else
  warn "未找到 $RJ（首次需手动创建）"
fi

echo ""
info "下一步（按需执行）："
echo "  1) 提交并打 tag：  git add -A && git commit -m 'release: v${NEW}' && git tag v${NEW} && git push --follow-tags"
echo "  2) 打核心包：      bash scripts/package-core.sh          # → release/cenkor-admin-core-${NEW}-*.tar.gz"
echo "  3) 推送 tag 自动发版：git push && git push --tags   # CI 自动打核心包 + 多架构镜像推 ghcr + 建 Release"
echo "  4) 中心端发布：    把新的 release.json 部署到官方云（hub），spoke 即可检测到 v${NEW}"
echo ""
echo -e "${GREEN}✓ 本地版本已就绪：${NEW}${NC}（记得同步更新「系统更新日志」公告）"
