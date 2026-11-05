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
#   bash scripts/release.sh sync         # 按当前 VERSION 对齐 release.json（修漂移）
#   bash scripts/release.sh sync --notes "..."   # 同上，顺便改说明
#   bash scripts/release.sh check        # 只检查是否漂移，不一致退出码 1（CI 可用）
#
# 设计要点（v0.5.20 事故后补）：
#   VERSION 与 release.json 是「同一件事的两半」，必须一次改完。
#   旧版在「VERSION 已是目标版本」时直接 exit 0，导致 VERSION 改了、
#   release.json 没改，tag 照打、Release 正文贴的是上一版说明。
# =============================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; DIM='\033[2m'; NC='\033[0m'
info() { echo -e "${GREEN}▸${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; }
dim()  { echo -e "${DIM}$1${NC}"; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
VF="backend/src/cenkor_admin/VERSION"
RJ="backend/src/cenkor_admin/release.json"
# 注意：Windows 上 core.autocrlf=true 会让工作区文件是 CRLF，
# 这里必须把 \r 一起去掉，否则会写出 "0.5.20\r" 这种毒值。
CUR="$(tr -d ' \r\n' < "$VF" 2>/dev/null || echo 0.0.0)"
JSON_VER="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1],encoding="utf-8")).get("version","").strip())' "$RJ" 2>/dev/null || echo "")"

TARGET="${1:-}"
[ -n "$TARGET" ] || { echo "用法: bash scripts/release.sh <版本|patch|minor|sync|check> [--notes \"...\"] [--date YYYY-MM-DD]"; exit 1; }
shift || true
NOTES=""
REL_DATE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --notes) NOTES="${2:-}"; [ $# -ge 2 ] && shift ;;
    --date)  REL_DATE="${2:-}"; [ $# -ge 2 ] && shift ;;
    "") ;;
    *) warn "忽略未知参数：$1" ;;
  esac
  shift
done
# 补记历史版本时用 --date 指定真实发版日，默认今天
[ -n "$REL_DATE" ] || REL_DATE="$(date +%Y-%m-%d)"

# ---------- check：只读，漂移即失败 ----------
run_check() {
  local ok=0
  echo "VERSION      : $CUR"
  echo "release.json : ${JSON_VER:-（缺失）}"
  if [ -z "$JSON_VER" ]; then
    err "release.json 缺少 version 字段"
    ok=1
  elif [ "$JSON_VER" != "$CUR" ]; then
    err "版本漂移：VERSION=$CUR 但 release.json=$JSON_VER"
    dim "  修复：bash scripts/release.sh sync"
    ok=1
  fi
  # notes 是 GitHub Release 正文来源，空值会让发版页变成一句空话
  local has_notes
  has_notes="$(python3 -c 'import json,sys; print(1 if json.load(open(sys.argv[1],encoding="utf-8")).get("notes","").strip() else 0)' "$RJ" 2>/dev/null || echo 0)"
  if [ "$has_notes" != "1" ]; then
    warn "release.json 的 notes 为空（Release 正文会没内容）"
  fi
  if [ "$ok" -eq 0 ]; then
    info "版本声明一致：$CUR"
  fi
  return "$ok"
}

case "$TARGET" in
  check) run_check || exit 1; exit 0 ;;
esac

# patch/minor/major 自动递增
bump() {
  local mode="$1" IFS='.'; set -- $CUR
  case "$mode" in
    patch) echo "$1.$2.$(( ${3%%-*} + 1 ))" ;;
    minor) echo "$1.$(( $2 + 1 )).0" ;;
    major) echo "$(( $1 + 1 )).0.0" ;;
  esac
}
case "$TARGET" in
  sync)               NEW="$CUR" ;;   # 不动版本号，只对齐声明
  patch|minor|major)  NEW="$(bump "$TARGET")" ;;
  *)                  NEW="$TARGET" ;;
esac

# 简单 semver 校验
echo "$NEW" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || { warn "版本号格式应为 x.y.z（当前：$NEW）"; exit 1; }

# ---------- 写 VERSION ----------
if [ "$NEW" != "$CUR" ]; then
  info "版本 bump：$CUR → $NEW"
  printf '%s\n' "$NEW" > "$VF"
  WROTE="$(tr -d ' \r\n' < "$VF")"
  [ "$WROTE" = "$NEW" ] || { err "VERSION 写入后读回不一致：$WROTE"; exit 1; }
else
  info "版本未变化：$NEW"
fi

# ---------- 同步 release.json（关键：无论版本是否变化都要执行）----------
TODAY="$REL_DATE"
if [ ! -f "$RJ" ]; then
  warn "未找到 $RJ（首次需手动创建），已跳过声明同步"
else
  # 输出一行摘要，供判断本次到底改了什么
  python3 - "$RJ" "$NEW" "$TODAY" "$NOTES" "$CUR" <<'PY'
import json, sys
p, ver, day, notes, old_ver = sys.argv[1:6]
d = json.load(open(p, encoding="utf-8"))
before = dict(d)
changed = []

if d.get("version") != ver:
    d["version"] = ver
    # released_at 只在版本号真的变化时推进，避免每次 sync 都把发版日期改到今天
    d["released_at"] = day
    changed.append("version %s → %s" % (before.get("version"), ver))
elif not d.get("released_at"):
    d["released_at"] = day
    changed.append("released_at 补为 %s" % day)

if notes and d.get("notes") != notes:
    d["notes"] = notes
    changed.append("notes 已更新")

if not d.get("notes", "").strip():
    print("WARN: notes 为空，GitHub Release 正文会是空的", file=sys.stderr)

if d != before:
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    # 补一个换行，避免某些编辑器/工具把文件尾巴吃掉
    with open(p, "a", encoding="utf-8") as f:
        f.write("\n")
    print("CHANGED:" + "; ".join(changed))
else:
    print("SAME:release.json 已与 VERSION 一致（%s）" % ver)
PY
fi

echo ""
if [ "$NEW" = "$CUR" ] && [ "${JSON_VER:-}" = "$NEW" ] && [ -z "$NOTES" ]; then
  info "无需改动：VERSION 与 release.json 都已是 $NEW"
  exit 0
fi

info "下一步（按需执行）："
echo "  1) 先自检：        bash scripts/release.sh check"
echo "  2) 提交并打 tag：  git add -A && git commit -m 'release: v${NEW}' && git tag v${NEW} && git push --follow-tags"
echo "  3) 打核心包：      bash scripts/package-core.sh          # → release/cenkor-admin-core-${NEW}-*.tar.gz"
echo "  4) 推送 tag 自动发版：git push && git push --tags   # CI 自动打核心包 + 多架构镜像推 ghcr + 建 Release"
echo "  5) 中心端发布：    把新的 release.json 部署到官方云（hub），spoke 即可检测到 v${NEW}"
echo ""
echo -e "${GREEN}✓ 本地版本已就绪：${NEW}${NC}（记得同步更新「系统更新日志」公告）"
