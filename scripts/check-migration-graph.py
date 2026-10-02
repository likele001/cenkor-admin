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
  · 引用到仓库里不存在的 revision  →  alembic upgrade head 直接 KeyError
  · 平白多出一个 head               →  alembic 拒绝执行
两种都会让「一键部署」表现为「容器全 healthy、数据库一张表都没建」。

本脚本只做三件事：无断链、无重复 revision、head 恰好一个。

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
        for name in sorted(os.listdir(versions_dir)):
            if name.endswith(".py") and not name.startswith("__"):
                files.append(os.path.join(versions_dir, name))

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

    ok = not errors and not broken and len(heads) == 1

    if args.quiet and ok:
        return 0

    mode = "git 跟踪（公开仓库视图）" if args.tracked_only else "工作区全部"
    print("迁移图自检 — 范围：%s" % mode)
    print("  文件数        : %d" % len(files))
    print("  revision 数   : %d" % len(revs))
    print("  head          : %s" % (", ".join(heads) if heads else "（无）"))
    print()

    if errors:
        print("✗ 解析问题：")
        for e in errors:
            print("    - %s" % e)
        print()

    if broken:
        print("✗ 断链（down_revision 指向仓库中不存在的迁移）：")
        for fname, rev, missing in broken:
            print("    - %s" % fname)
            print("        revision      = %s" % rev)
            print("        缺失的 down    = %s" % missing)
        print()
        print("  可能原因：该迁移被提交在了「闭源链」中间，而闭源迁移不进公开仓库。")
        print("  修法：把它的 down_revision 改挂到公开链的 head 上，"
              "并把原闭源子链的挂载点顺延。")
        print()

    if len(heads) == 0:
        print("✗ 没有 head —— 迁移图全是环或全断。")
        print()
    elif len(heads) > 1:
        print("✗ head 不唯一（alembic 要求恰好 1 个）：")
        for h in heads:
            print("    - %s  (%s)" % (h, revs.get(h, "?")))
        print()
        print("  可能原因：两条互不相交的迁移链同时存在（典型是闭源链与公开链各一个 head）。")
        print("  修法：把公开链的 head 挂到闭源链的尾端，或反之。")
        print()

    if ok:
        print("✓ 迁移图完整：无断链、无重复、head 唯一（%s）" % heads[0])
        return 0

    print("✗ 迁移图自检未通过。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
