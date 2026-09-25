#!/usr/bin/env bash
# 提交前自检：找出「落在内置目录、却既没被 git 跟踪、也没被 .gitignore 忽略」的应用。
#
# 这类应用处于「裸未跟踪」状态 —— 一次 git add -A 就会把源码与前端产物
# 一起提交进【公开仓库】。
#
# 背景：仓库有两条应用落点，安全性不同 ——
#   · backend/src/apps/<key>/                 外置目录，.gitignore 整体忽略，漏不了
#   · backend/src/cenkor_admin/apps/<key>/    内置目录，默认进库，商业应用须逐条登记
# 本脚本守的是第二条。
#
# 用法：
#   bash scripts/check-app-tracking.sh            # 有问题时退出码 1
#   bash scripts/check-app-tracking.sh --quiet    # 正常时不输出（供 hook 用）
#
# 已挂到 .githooks/pre-commit（启用方式：git config core.hooksPath .githooks）

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

BASES=(
  "backend/src/cenkor_admin/apps"
  "backend/src/cenkor_admin/static/apps"
)

bad=()
for base in "${BASES[@]}"; do
  [ -d "$base" ] || continue
  for d in "$base"/*/; do
    [ -d "$d" ] || continue
    key="$(basename "$d")"
    case "$key" in __pycache__|.*) continue ;; esac

    # 已被 .gitignore 忽略 → 商业应用已登记，安全
    git check-ignore -q "$base/$key" && continue
    # 已有文件在版本库里 → 开源应用，安全
    [ "$(git ls-files -- "$base/$key" | wc -l)" -gt 0 ] && continue
    # 目录里没有实体文件 → 跳过
    [ "$(find "$d" -type f -not -path '*/__pycache__/*' | wc -l)" -eq 0 ] && continue

    bad+=("$base/$key")
  done
done

if [ "${#bad[@]}" -eq 0 ]; then
  [ "$QUIET" -eq 0 ] && echo "✓ 应用跟踪状态正常：无裸未跟踪的应用目录"
  exit 0
fi

echo ""
echo "✗ 发现 ${#bad[@]} 个应用处于「裸未跟踪」状态 —— 既没被 git 跟踪，也没被 .gitignore 忽略："
echo ""
for p in "${bad[@]}"; do
  echo "    $p/    ($(find "$p" -type f -not -path '*/__pycache__/*' | wc -l) 个文件)"
done
echo ""
echo "  ⚠️ 一旦 git add -A，这些源码与前端产物就会提交进【公开仓库】。"
echo ""
echo "  请二选一："
echo "    · 开源应用  →  git add <上面的路径>"
echo "    · 商业闭源  →  在 .gitignore 登记三行（照抄其中已有应用）："
echo "          backend/src/cenkor_admin/apps/<key>/"
echo "          backend/src/cenkor_admin/static/apps/<key>/"
echo "          backend/alembic/versions/2026*_<key>*.py"
echo ""
exit 1
