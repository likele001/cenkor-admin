#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""alembic 迁移图自检 —— 防止「一条命令部署后库是空的」再次发生。

背景
----
本仓库的迁移文件分两类：
  · 开源迁移            backend/alembic/versions/*.py      进公开仓库
  · 商业应用迁移        payment / commerce / erp / crm / …  被 .gitignore 排除，不进库

如果把「平台自己的迁移」挂在「闭源链」的正中间，公开仓库被 gitignore 掉闭源部分后，
那个迁移就成了孤儿，后果是：
  · 引用到仓库里不存在的 revision  →  alembic 直接 KeyError
  · 平白多出一个 head               →  alembic 拒绝执行
两种都会让「一键部署」表现为「容器全 healthy、数据库一张表都没建」。

本脚本只做四件事：无断链、无重复 revision、head 恰好一个、revision 不超长。

判定规则（v0.5.11 开源 payment/commerce 后调整）
--------------------------------------------------
硬约束只有一条：**git 跟踪的迁移（公开子图）必须恰好 1 个 head、无断链**。
公开仓库拉下来要能 `alembic upgrade head` 一把建库，这条破了就是事故。

全量视图（含闭源迁移）**允许多个 head**：闭源应用（erp / crm / mes / workflow /
collect）是并行开发线，各自一个 head 是正常形态，不必强迫合流。全量视图只额外
校验一件事 —— 每个 head 都能沿 down_revision 回到公开 head，即没有任何一条
闭源链是与公开链平行的孤链（那样公开仓库拿到它会断链）。

历史背景：早期是「公开链 + 一条闭源链 + 挂载点顺延」的单 head 模型，
新增公开迁移必须顺延挂载迁移的 down_revision。v0.5.11 把 payment/commerce
开源时改成合流迁移（20261103_1200_merge_commerce），闭源侧随后拆成 3 条独立
链并再次合流（20261103_1300_merge_closed，闭源文件、不进库）。
这个「挂载点」概念仍未完全退场，见 docs/migrations.md。

完整规则、新增迁移的执行顺序与事故复盘：docs/migrations.md

用法
----
  python3 scripts/check-migration-graph.py                  # 检查工作区全部迁移
  python3 scripts/check-migration-graph.py --tracked-only   # 只看 git 跟踪的（= 公开仓库的样子）
  python3 scripts/check-migration-graph.py --quiet          # 正常时不输出（供 hook / CI 用）

退出码：0 = 通过，1 = 失败。
已挂到 .githooks/pre-commit（启用：git config core.hooksPath .githooks）。
"""
from __future__ import annotations

import argparse
import ast
import io
import os
import subprocess
import sys

DEFAULT_DIR = "backend/alembic/versions"

# alembic 把 alembic_version.version_num 建成 VARCHAR(32)（见 alembic.runtime.migration）。
# revision 超过 32 字符时，upgrade/stamp 会在 UPDATE 那一步报 StringDataRightTruncation，
# 而且要到跑迁移时才发现 —— 所以在提交前就拦住。
MAX_REV_LEN = 32


def _literal(node):
    """安全求值：只接受字符串 / None / 元组字面量。"""
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def parse_migration(path):
    """解析单个迁移文件的 (revision, down_revision)。

    用 AST 而不是 import —— 避免执行模块副作用，也不要求依赖已安装。
    同时兼容 `x = "..."` 与 `x: str = "..."` 两种写法。
    """
    try:
        tree = ast.parse(io.open(path, encoding="utf-8").read())
    except SyntaxError as exc:
        return None, None, "语法错误：%s" % exc

    rev = down = None
    found_rev = found_down = False
    for node in tree.body:
        pairs = []
        if isinstance(node, ast.Assign):
            pairs = [(t, node.value) for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            pairs = [(node.target, node.value)]
        for target, value in pairs:
            if target.id == "revision":
                rev, found_rev = _literal(value), True
            elif target.id == "down_revision":
                down, found_down = _literal(value), True

    if not found_rev:
        return None, None, "未找到 revision 变量"
    return rev, down, None


def collect(versions_dir, tracked_only):
    """返回 (maps, files, errors)。"""
    files = []
    if os.path.isdir(versions_dir):
        # 迁移已按应用分到子目录（core / erp / crm / mes / commerce / ext），
        # 必须递归，否则只在根目录找 .py 会一个都找不到。
        for root, _dirs, names in os.walk(versions_dir):
            if "__pycache__" in root:
                continue
            for name in sorted(names):
                if name.endswith(".py") and not name.startswith("__"):
                    files.append(os.path.join(root, name))

    if tracked_only:
        try:
            out = subprocess.run(
                ["git", "ls-files", versions_dir],
                capture_output=True, text=True, check=False,
            ).stdout
        except FileNotFoundError:
            out = ""
        tracked = {os.path.normpath(p) for p in out.splitlines() if p.endswith(".py")}
        files = [f for f in files if os.path.normpath(f) in tracked]

    revs = {}          # revision -> 文件名
    downs = {}         # revision -> down_revision（规范化成 tuple）
    errors = []
    for path in files:
        rev, down, err = parse_migration(path)
        base = os.path.basename(path)
        if err:
            errors.append("%s：%s" % (base, err))
            continue
        if rev is None:
            errors.append("%s：revision 为空" % base)
            continue
        if rev in revs:
            errors.append("重复的 revision %r：%s 与 %s" % (rev, revs[rev], base))
            continue
        if len(rev) > MAX_REV_LEN:
            errors.append(
                "revision %r 长 %d 字符，超过 alembic_version.version_num 的 %d 字符上限："
                "upgrade/stamp 会报 StringDataRightTruncation（%s）"
                % (rev, len(rev), MAX_REV_LEN, base)
            )
            continue
        revs[rev] = base
        if down is None:
            downs[rev] = ()
        elif isinstance(down, (list, tuple)):
            downs[rev] = tuple(down)
        else:
            downs[rev] = (down,)
    return revs, downs, files, errors


def analyse(revs, downs):
    """返回 (断链列表, head 列表)。"""
    known = set(revs)
    referenced = set()
    broken = []
    for rev, parents in downs.items():
        for parent in parents:
            referenced.add(parent)
            if parent not in known:
                broken.append((revs[rev], rev, parent))
    # head = 自己的 revision 不被任何迁移当作 down_revision
    heads = sorted(r for r in known if r not in referenced)
    return broken, heads


def ancestors(rev, downs):
    """沿 down_revision 回溯，返回祖先闭包（含自身）。"""
    seen, stack = set(), [rev]
    while stack:
        r = stack.pop()
        if r in seen:
            continue
        seen.add(r)
        stack.extend(downs.get(r, ()))
    return seen


def main():
    ap = argparse.ArgumentParser(description="alembic 迁移图自检")
    ap.add_argument("--dir", default=DEFAULT_DIR, help="迁移目录（默认 %s）" % DEFAULT_DIR)
    ap.add_argument("--tracked-only", action="store_true",
                    help="只检查 git 跟踪的迁移文件（= 公开仓库看到的样子）")
    ap.add_argument("--quiet", action="store_true", help="通过时不输出")
    args = ap.parse_args()

    if not os.path.isdir(args.dir):
        print("✗ 迁移目录不存在：%s" % args.dir, file=sys.stderr)
        return 1

    revs, downs, files, errors = collect(args.dir, args.tracked_only)
    if not files:
        print("✗ 没找到任何迁移文件（目录：%s）" % args.dir, file=sys.stderr)
        return 1

    broken, heads = analyse(revs, downs)

    # 公开子图：任何模式下都要单独算一次。公开仓库一旦断链或多 head，
    # 「一键部署」会直接失败 —— 这是唯一的硬约束。
    if args.tracked_only:
        pbroken, pheads, pcount = broken, heads, len(files)
    else:
        _pr, _pd, pfiles, _pe = collect(args.dir, tracked_only=True)
        pbroken, pheads = analyse(_pr, _pd)
        pcount = len(pfiles)

    problems = []
    if errors:
        problems.append(("parse", errors))

    # 公开子图断链比全量断链更致命：工作区里父节点在、git 里不在，
    # 「本地跑得好好的」，clone 下来直接 KeyError。
    pset = {(f, r, m) for f, r, m in pbroken}
    bset = {(f, r, m) for f, r, m in broken}
    if pset:
        problems.append(("public_broken", pbroken))
    if bset - pset:
        problems.append(("broken", [x for x in broken if x in bset - pset]))

    if not pheads:
        problems.append(("no_public_head", []))
    elif len(pheads) > 1:
        problems.append(("multi_public_head", pheads))

    # 每个 head 都必须能回到公开 head，否则是一条与公开链平行的孤链。
    if not args.tracked_only and len(pheads) == 1:
        pub = pheads[0]
        orphan = [h for h in heads if pub not in ancestors(h, downs)]
        if orphan:
            problems.append(("orphan_head", orphan))

    # 公开视图必须恰好 1 个 head；全量视图允许多个（闭源并行开发线）。
    if args.tracked_only and len(heads) != 1:
        problems.append(("multi_head", heads))

    ok = not problems
    if args.quiet and ok:
        return 0

    mode = "git 跟踪（公开仓库视图）" if args.tracked_only else "工作区全部"
    print("迁移图自检 — 范围：%s" % mode)
    print("  文件数        : %d" % len(files))
    print("  revision 数   : %d" % len(revs))
    print("  head          : %s" % (", ".join(heads) if heads else "（无）"))
    if not args.tracked_only:
        print("  公开子图      : %d 个文件，head %s"
              % (pcount, ", ".join(pheads) if pheads else "（无）"))
    print()

    for kind, payload in problems:
        if kind == "parse":
            print("✗ 解析问题：")
            for e in payload:
                print("    - %s" % e)
            print()
        elif kind == "public_broken":
            print("✗ 公开子图断链（公开迁移的 down_revision 不在 git 跟踪的文件里）：")
            for fname, rev, missing in payload:
                print("    - %s" % fname)
                print("        revision      = %s" % rev)
                print("        缺失的 down    = %s" % missing)
            print()
            print("  这是最危险的一种：工作区里父节点在、clone 下来不在，")
            print("  本地一切正常，部署时 alembic 直接 KeyError。")
            print()
            print("  修法：公开迁移只能依赖公开 revision。要接闭源段，")
            print("  用合流迁移挂到公开 head 上，别直接指向闭源 revision。")
            print()
        elif kind == "broken":
            print("✗ 断链（down_revision 指向仓库中不存在的迁移）：")
            for fname, rev, missing in payload:
                print("    - %s" % fname)
                print("        revision      = %s" % rev)
                print("        缺失的 down    = %s" % missing)
            print()
            print("  可能原因：该迁移被提交在了「闭源链」中间，而闭源迁移不进公开仓库。")
            print("  修法：把它的 down_revision 改挂到公开链的 head 上，"
                  "并把原闭源子链的挂载点顺延。")
            print()
        elif kind == "no_public_head":
            print("✗ 公开子图没有 head —— 全是环或全断。")
            print()
        elif kind == "multi_public_head":
            print("✗ 公开仓库视图出现多个 head（alembic 要求恰好 1 个）：")
            for h in payload:
                print("    - %s  (%s)" % (h, revs.get(h, "?")))
            print()
            print("  可能原因：公开链新增了迁移，但没把闭源链的挂载点顺延到新 head，")
            print("  或某条公开迁移被误改成依赖闭源 revision。")
            print("  修法：git 跟踪的迁移必须串成单 head，闭源部分挂在它之下。")
            print()
        elif kind == "orphan_head":
            print("✗ 有 head 回不到公开链（是一条与公开链平行的孤链）：")
            for h in payload:
                print("    - %s  (%s)" % (h, revs.get(h, "?")))
            print()
            print("  每条链最终都必须接在公开 head 之后，否则公开仓库拿到它会断链。")
            print()
        elif kind == "multi_head":
            print("✗ head 不唯一（公开视图必须恰好 1 个）：")
            for h in payload:
                print("    - %s  (%s)" % (h, revs.get(h, "?")))
            print()

    if ok:
        if args.tracked_only:
            print("✓ 迁移图完整：无断链、无重复、head 唯一（%s）" % heads[0])
        else:
            print("✓ 迁移图完整：公开子图单 head（%s），全量 %d 个 head 均可达公开链"
                  % (pheads[0], len(heads)))
        return 0

    print("✗ 迁移图自检未通过。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
