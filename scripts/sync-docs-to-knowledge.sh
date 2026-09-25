#!/bin/bash
# ============================================================
# 把本仓库 docs/ 同步到知识库站点（docs.user.023ent.net）
#
# 单一真相源：本仓库 docs/ 是唯一来源，站点目录只是产物。
# ⚠️ 不要直接编辑 /www/wwwroot/knowledge/docs/cenkor-admin/ 下的文件，
#    下次同步会被覆盖。
#
# 命名约定：仓库文档文件名**一律小写**（2026-09-25 统一）。
#   站点 URL 由文件名直接决定，大写名会产出 /cenkor-admin/DEPLOY 这类形态，
#   且同目录出现只差大小写的一对文件时会让 Rollup 改名 chunk →
#   构建报 ERR_MODULE_NOT_FOUND（详见 refs/cenkor-docs.md §四.3）。
#   唯一例外：仓库根 README.md 保留大写（GitHub 约定，外部 blob 链接依赖它），
#   同步到站点时小写化为 readme.md。
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "$SCRIPT_DIR/.." && pwd)"
DEST="/www/wwwroot/knowledge/docs/cenkor-admin"
KNOWLEDGE="/www/wwwroot/knowledge"

[ -d "$DEST" ] || { echo "✗ 站点目录不存在: $DEST"; exit 1; }
[ -f "$SRC/docs/deploy.md" ] || { echo "✗ 源目录不对（缺 docs/deploy.md）: $SRC"; exit 1; }

echo "▸ 清理旧文档..."
# ⚠️ 用 -iname 而不是 -name：站点目录里可能残留历史的大写文件（如 README.md、
#    或改名前的 INDEX.md），普通 *.md 通配匹配不到它们，残骸会跨次同步存活，
#    并触发下面的大小写撞名。
find "$DEST" -mindepth 1 -maxdepth 1 -iname '*.md' -delete
rm -rf "$DEST/archive" "$DEST/apps" "$DEST/addons" "$DEST/release"
rm -rf "$DEST"/[0-9][0-9]-*/   # 数字前缀目录每轮重建（见下方「用户手册」说明）

echo "▸ 复制仓库根级文档..."
cp "$SRC/README.md" "$DEST/readme.md"   # 仓库保留大写，站点侧小写化
cp "$SRC/architecture.md" "$DEST/architecture.md"
[ -f "$SRC/admin_system_comparison.md" ] && cp "$SRC/admin_system_comparison.md" "$DEST/"

echo "▸ 复制 docs/ 主文档..."
# 文件名已统一小写，直接整体拷贝即可（docs/index.md 会落在 $DEST/index.md，
# 即站点 /cenkor-admin/ 的目录首页）。
cp "$SRC/docs"/*.md "$DEST/"

echo "▸ 复制子目录..."
# ⚠️ archive/ 不上线：它是已归档历史文档，其中的模板语法 {{ }} 会被 VitePress 的
#    Vue 编译器当成插值解析而报错；归档本就不该出现在站点上。
for d in apps addons release; do
  if [ -d "$SRC/docs/$d" ]; then
    mkdir -p "$DEST/$d"
    find "$SRC/docs/$d" -maxdepth 1 -name '*.md' -exec cp {} "$DEST/$d/" \;
    echo "    $d/ → $(find "$DEST/$d" -name '*.md' | wc -l) 份"
  fi
done

# ★ 数字前缀目录（`NN-中文名/`）：站点侧栏对这类目录**原样列出、完全不过滤**，
#   是放「用户使用教程」的唯一正路 —— 根级散文档必须命中 GROUPS 关键词才显示，
#   而教程类命名（含"教程""使用指南"）还会被 NON_TECH 主动排除、静默消失。
#   判据与站点侧一致：两位数字 + `-`。
for d in "$SRC/docs"/[0-9][0-9]-*/; do
  [ -d "$d" ] || continue          # glob 未命中时是字面量，跳过
  name="$(basename "$d")"
  mkdir -p "$DEST/$name"
  find "$d" -maxdepth 1 -name '*.md' -exec cp {} "$DEST/$name/" \;
  echo "    $name/ → $(find "$DEST/$name" -name '*.md' | wc -l) 份"
done

# ℹ️ 这里曾生成 index.md 的副本「项目自述-index.md」，本意是在侧栏加一个「项目自述」入口。
#    2026-09-25 移除：侧栏归组靠 classify() 按**文件名关键词**匹配，
#    该名字不命中任何分组 → 压根没进侧栏，只留一个与目录首页内容完全相同、无入口的孤儿页。
#    目录首页点侧栏顶部的项目名即可到达，无需重复条目。

echo "▸ 后处理：修正站内链接（死链降级为纯文本，否则构建会失败）..."
python3 "$SRC/scripts/fix-site-links.py" "$DEST"

echo "▸ 同步结果..."
ls -1 "$DEST"/*.md | while read -r f; do printf '    %s\n' "$(basename "$f")"; done

echo "▸ 构建站点..."
cd "$KNOWLEDGE"

# ⚠️ 自检：同一目录下若有只差大小写的 .md 文件（历史上是 INDEX.md + index.md），
#    Rollup 会给其中一个 chunk 追加哈希改名，渲染阶段 import 原名字必然
#    ERR_MODULE_NOT_FOUND。命名已统一小写，这里是防御性拦截。
COLLISIONS="$(find docs -type f -name '*.md' -printf '%p\n' \
  | awk '{print tolower($0)"\t"$0}' | sort \
  | awk -F'\t' '{if($1==p) print "    "pv"  <->  "$2; p=$1; pv=$2}')"
if [ -n "$COLLISIONS" ]; then
  echo "✗ 站点文档存在大小写撞名，构建必然失败："
  echo "$COLLISIONS"
  echo "  请把其中一个改名（通常是不该上线的那份），然后重跑本脚本。"
  exit 1
fi

# 教程覆盖度自检：列出「还没有用户手册」的应用。
# 只警告不阻断 —— 教程是逐步补齐的，阻断会让人上不了线。
# 等覆盖齐了，把下面的 exit 1 打开即可变成硬性关卡。
echo "▸ 校验：应用用户手册覆盖度..."
MANUAL_DIR="$SRC/docs/05-用户手册"
MISSING=""
N_TOTAL=0
if [ -d "$MANUAL_DIR" ]; then
  for m in "$SRC"/backend/src/cenkor_admin/apps/*/manifest.py; do
    [ -f "$m" ] || continue
    N_TOTAL=$((N_TOTAL + 1))
    key="$(grep -oE 'key="[^"]+"' "$m" | head -1 | sed 's/key="//; s/"$//')"
    [ -n "$key" ] || continue
    ls "$MANUAL_DIR/$key"*.md >/dev/null 2>&1 || MISSING="$MISSING $key"
  done
fi
if [ -n "$MISSING" ]; then
  echo "    ⚠️ $((N_TOTAL - $(echo "$MISSING" | wc -w))) / $N_TOTAL 个应用已有用户手册，缺这些："
  for k in $MISSING; do echo "       - $k"; done
  echo "       → 补法：$MANUAL_DIR/<key>_操作手册.md"
else
  echo "    ✓ $N_TOTAL 个应用的用户手册全部就位"
fi

# ⚠️ 直接调 vitepress 二进制，不要用 `pnpm docs:build`：
#    本目录 node_modules 是用 npm 装的，pnpm 会先做依赖检查、
#    把包移到 .ignored 并因 esbuild 构建脚本未审批而报错中止。
# 清 .temp/cache：本目录长期在增量状态下构建，残留旧 chunk 会干扰新页面的文件名解析。
rm -rf docs/.vitepress/.temp docs/.vitepress/cache
if [ -x node_modules/.bin/vitepress ]; then
  node_modules/.bin/vitepress build docs
else
  echo "  ⚠️ 未找到 node_modules/.bin/vitepress，回退 npm run docs:build"
  npm run docs:build
fi

echo "▸ 修正属主（避免 www 后续无法覆盖）..."
chown -R www:www "$DEST" "$KNOWLEDGE/docs/.vitepress/dist"

echo ""
echo "✅ 同步完成"
echo "   https://docs.user.023ent.net/cenkor-admin/"
