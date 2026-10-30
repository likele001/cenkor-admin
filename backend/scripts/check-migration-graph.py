#!/usr/bin/env python3
"""迁移图体检：把「多 head」这件真事讲清楚。

背景
----
`codegen/builder.py` 在生成新迁移时会算 head，若某个 scope 内出现多个 head
就报错「先修链为唯一 head（参考 scripts/check-migration-graph.py）」——
但这个脚本之前并不存在，是一处悬空引用。

本脚本要澄清的核心认知：**这个项目的迁移图不是一条线，是 6 条链交织成一棵树。**
- 按目录（scope）单独算，会得到多个「局部 head」——这是**正常**的，
  跨目录挂载让不同链的终点落在不同目录里；
- 只有把全量图（所有目录 + 跨目录的 down_revision 关系）合起来看，
  才是唯一 1 个 head、1 个 base。

所以「多个 head」不是错误，是结构本身。真正要报的是：
断链（down_revision 指向不存在的 revision）、环、以及某个 scope 的局部 head
在全量图里其实已被子节点接管（此时 codegen 往该 scope 追加会挂错位置）。

用法
----
    python scripts/check-migration-graph.py            # 人读报告
    python scripts/check-migration-graph.py --json     # 机读结果
    python scripts/check-migration-graph.py --root DIR # 指定 alembic/versions 位置

退出码：0 = 全量图健康（1 head / 无断链 / 无环）；1 = 有结构问题。
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace

DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "alembic" / "versions"


# ────────────────────────────── 解析 ──────────────────────────────


def _safe_literal(node):
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def parse_migration(path: Path):
    """抽出 revision / down_revision。口径与 codegen/builder.py 保持一致。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return None, None
    rev = down = None
    found = False
    for node in tree.body:
        pairs = []
        if isinstance(node, ast.Assign):
            pairs = [(t, node.value) for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            pairs = [(node.target, node.value)]
        for target, value in pairs:
            if target.id == "revision":
                rev = _safe_literal(value)
                found = True
            elif target.id == "down_revision":
                down = _safe_literal(value)
    if not found:
        return None, None
    return rev, down


def _norm_down(down):
    """down_revision 允许是 str / None / list，统一成 list[str]。"""
    if down is None:
        return []
    if isinstance(down, str):
        return [down]
    if isinstance(down, (list, tuple)):
        return [str(x) for x in down]
    return []


def load_graph(root: Path):
    """扫描版本目录，返回节点表。"""
    nodes: dict[str, dict] = {}
    if not root.is_dir():
        raise SystemExit(f"✗ 迁移目录不存在：{root}")

    for f in sorted(root.rglob("*.py")):
        if f.name.startswith("__"):
            continue
        if f.parent == root:
            scope = "(root)"
        else:
            scope = f.parent.relative_to(root).as_posix()
        rev, down = parse_migration(f)
        if rev is None:
            continue
        if rev in nodes:
            print(f"! revision 重复：{rev}  ({nodes[rev]['file']} / {f})", file=sys.stderr)
        nodes[rev] = {
            "revision": rev,
            "down": _norm_down(down),
            "scope": scope,
            "file": f.relative_to(root.parent).as_posix(),
        }
    return nodes


# ────────────────────────────── 分析 ──────────────────────────────


def analyze(nodes: dict[str, dict]):
    children: dict[str, list[str]] = {r: [] for r in nodes}
    dangling: list[dict] = []

    for rev, n in nodes.items():
        for d in n["down"]:
            if d in nodes:
                children[d].append(rev)
            else:
                dangling.append({"revision": rev, "missing_down": d, "scope": n["scope"]})

    # 局部 head：scope 内没被 scope 内其它节点引用的 revision
    # （与 codegen/builder.py 的 _compute_head 口径一致：只看 scope 内的 down 关系）
    scoped_refs: dict[str, set[str]] = {}
    for n in nodes.values():
        scoped_refs.setdefault(n["scope"], set())
        for d in n["down"]:
            if d in nodes and nodes[d]["scope"] == n["scope"]:
                scoped_refs[n["scope"]].add(d)

    scopes: dict[str, dict] = {}
    for rev, n in nodes.items():
        s = scopes.setdefault(n["scope"], {"count": 0, "heads": [], "bases": []})
        s["count"] += 1
        if rev not in scoped_refs[n["scope"]]:
            s["heads"].append(rev)
        if not n["down"]:
            s["bases"].append(rev)
    for s in scopes.values():
        s["heads"].sort()
        s["bases"].sort()

    # 全量 head：没有任何子节点的 revision
    full_heads = sorted(r for r in nodes if not children[r])
    full_bases = sorted(r for r, n in nodes.items() if not n["down"])

    # 跨目录挂载点：down_revision 落在别的 scope
    cross_mounts = []
    for rev, n in sorted(nodes.items()):
        for d in n["down"]:
            if d in nodes and nodes[d]["scope"] != n["scope"]:
                cross_mounts.append({
                    "revision": rev,
                    "scope": n["scope"],
                    "down": d,
                    "down_scope": nodes[d]["scope"],
                })

    # 环检测
    cycles = _find_cycles(nodes, children)

    # scope 的局部 head 是否已被全量图的子节点接管（codegen 追加会挂错位置）
    shadowed = []
    for scope, s in scopes.items():
        for h in s["heads"]:
            if children[h]:
                shadowed.append({
                    "scope": scope,
                    "head": h,
                    "children": sorted(children[h]),
                })

    return {
        "children": children,
        "scopes": scopes,
        "full_heads": full_heads,
        "full_bases": full_bases,
        "dangling": dangling,
        "cross_mounts": cross_mounts,
        "cycles": cycles,
        "shadowed": shadowed,
    }


def _find_cycles(nodes, children) -> list[list[str]]:
    """DFS 三色标记找环。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {r: WHITE for r in nodes}
    stack: list[str] = []
    cycles: list[list[str]] = []

    def visit(r: str):
        color[r] = GRAY
        stack.append(r)
        for c in children[r]:
            if color[c] == GRAY:
                idx = stack.index(c)
                cycles.append(stack[idx:] + [c])
            elif color[c] == WHITE:
                visit(c)
        stack.pop()
        color[r] = BLACK

    for r in sorted(nodes):
        if color[r] == WHITE:
            visit(r)
    return cycles


# ────────────────────────────── 输出 ──────────────────────────────


def render(nodes, analysis, root) -> None:
    # SimpleNamespace 不支持 ** 解包，两种入参都接住
    a = analysis if isinstance(analysis, SimpleNamespace) else SimpleNamespace(**analysis)
    a.root = root
    total = len(nodes)
    print("═" * 68)
    print("  迁移图体检")
    print("═" * 68)
    print(f"根目录: {a.root}")
    print(f"迁移总数: {total}\n")

    print("【全量图】把跨目录的 down_revision 一并算进来，才是真实的 head。")
    print(f"  base (无 down_revision): {len(a.full_bases)}")
    for r in a.full_bases:
        print(f"    - {r}  [{nodes[r]['scope']}]  {nodes[r]['file']}")
    print(f"  head (无子节点)       : {len(a.full_heads)}")
    for r in a.full_heads:
        print(f"    - {r}  [{nodes[r]['scope']}]  {nodes[r]['file']}")
    if len(a.full_heads) > 1:
        print("  ⚠ 全量 head 不唯一 —— 分支已产生，需要人工确认挂载点")
    print()

    print("【按目录看局部 head】多 head 在这里是正常的：不同链的终点落在不同目录。")
    for scope in sorted(a.scopes):
        s = a.scopes[scope]
        mark = " ⚠ codegen 在此 scope 追加会因多 head 报错" if len(s["heads"]) > 1 else ""
        print(f"  {scope:<10} {s['count']:>3} 个迁移   局部 head {len(s['heads'])} 个{mark}")
        for h in s["heads"]:
            extra = ""
            kids = sorted(a.children.get(h) or [])
            if kids:
                extra = f"   ← 已被 {', '.join(kids)} 接管（链的中间段）"
            else:
                extra = "   ← 全量图终点"
            print(f"      - {h}{extra}")
    print()

    print("【codegen 挂载点】新迁移的 down_revision 该挂哪 —— 别挂错位置。")
    if len(a.full_heads) == 1:
        h = a.full_heads[0]
        print(f"  ✓ 应挂在：{h}  [scope={nodes[h]['scope']}]")
        print("     这是全量图唯一 head，也是它所在 scope 内唯一没被接管的局部 head。")
        others = [s for s in a.shadowed]
        if others:
            print(f"  其余 {len(others)} 个局部 head 都已被跨目录节点接管（链中间段），")
            print("     往那些 scope 追加会让新迁移落在链的中段、后续 head 判定失效。")
    else:
        print("  ⚠ 全量 head 不唯一，先修挂载点再生成新迁移")
    print()

    print("【跨目录挂载点】down_revision 落在别的目录 —— 多链交织的实际连接处。")
    if a.cross_mounts:
        for m in a.cross_mounts:
            print(f"  {m['scope']}/{m['revision']}")
            print(f"      └─ down → {m['down_scope']}/{m['down']}")
    else:
        print("  (无)")
    print()

    problems = 0
    print("【结构问题】")
    if a.dangling:
        problems += len(a.dangling)
        print("  ✗ 断链 —— down_revision 指向不存在的 revision：")
        for d in a.dangling:
            print(f"      {d['scope']}/{d['revision']} → {d['missing_down']}")
    if a.cycles:
        problems += len(a.cycles)
        print("  ✗ 环：")
        for c in a.cycles:
            print("      " + " → ".join(c))
    if not problems:
        print("  ✓ 无断链、无环")
    print()
    print("═" * 68)
    print("  结论：全量 head 唯一 = 1（结构健康）"
          if len(a.full_heads) == 1 and not problems
          else f"  结论：需要处理 {problems} 个结构问题")
    print("═" * 68)


def main() -> int:
    ap = argparse.ArgumentParser(description="迁移图体检：全量 head + 各 scope 局部 head + 跨目录挂载")
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="alembic/versions 目录")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    nodes = load_graph(args.root)
    if not nodes:
        print("✗ 没解析到任何迁移", file=sys.stderr)
        return 1
    a = SimpleNamespace(**analyze(nodes))

    if args.json:
        print(json.dumps({
            "total": len(nodes),
            "full_heads": a.full_heads,
            "full_bases": a.full_bases,
            "scopes": {k: v for k, v in sorted(a.scopes.items())},
            "cross_mounts": a.cross_mounts,
            "dangling": a.dangling,
            "cycles": a.cycles,
            "shadowed": a.shadowed,
            "healthy": len(a.full_heads) == 1 and not a.dangling and not a.cycles,
        }, ensure_ascii=False, indent=2))
    else:
        render(nodes, a, args.root)

    return 0 if (len(a.full_heads) == 1 and not a.dangling and not a.cycles) else 1


if __name__ == "__main__":
    sys.exit(main())
