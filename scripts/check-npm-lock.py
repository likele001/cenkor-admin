#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""npm workspace ↔ package-lock 一致性检查 —— 防止「lock 悄悄残缺、本地无法 npm ci」。

背景
----
本仓库踩过一次很贵的坑（2026-11-11）：

  `c075dab` 把 **admin-web** 的 Tiptap 从 2 升到 3.33.0，同时重生成
  `package-lock.json`。但 **developer-web** 的 `package.json` 仍声明
  `@tiptap/*: ^2.27.2`（14 个包）。重生成 lock 时，developer-web 需要的
  Tiptap 2.x **实体节点被整段删掉**（lock 里 `"version": "2.27` 计数 = 0）。

  结果：仓库根任何一次 `npm ci` 都被全量校验直接拒绝——

      npm error Missing: @tiptap/core@2.27.3 from lock file
      npm error Missing: vue-tsc@2.2.12 from lock file
      ...（共 35 条）

  本地从此无法重建前端，只能靠手工 `npm install --package-lock-only` 抢救。

为什么 CI 没发现
----------------
`.github/workflows/ci.yml` 的前端 job 是 **matrix + working-directory**：

    matrix: { app: [admin-web, portal-web] }
    defaults.run.working-directory: frontend/${{ matrix.app }}

在子目录里跑 `npm ci` 时，npm 只会安装**该 workspace 实际需要的**依赖；
一个"磁盘上不存在"的 workspace 的节点缺失，它根本不去校验。于是缺口
一路绿灯过审。

**注意**：`frontend/developer-web/` 是刻意不入库的闭源商业资产（见
`.gitignore` 的说明），CI 从 git checkout 后它不存在。所以本脚本对每个
workspace 分两种来源校验：

  ▶ 磁盘上有 package.json（开发者本地 / 有源码的机器）
        → 以 package.json 为准，最权威。缺节点、版本不符、声明不同步全查。

  ▶ 磁盘上没有源码，但 **lock 里自带该 workspace 的声明块**（CI 的常态）
        → 以 lock 自带的 dependencies/devDependencies 为准，只查「声明了但
          没有实体节点」。这恰好能抓住 2026-11-11 那个 bug：lock 里
          `frontend/developer-web` 块声明了 28 个依赖，其中 15 个没有节点。
        → 这一路是**只读 lock 的**，不需要源码，所以 CI 也能拦住。

也就是说：同一份残缺 lock，在开发者机器上查得更细，在 CI 上至少能查
「声明 vs 实体节点」这一层 —— 而那正是当初漏掉的那一层。

判定
----
  MISSING_DEP        workspace 声明的依赖，lock 里找不到任何节点   → 失败
  VERSION_MISMATCH   lock 有节点，但版本不满足声明范围             → 失败
  STALE_DECL         lock 里该 workspace 的依赖清单与 package.json 不同步 → 失败
  REGISTRY_DRIFT     lock 里 resolved 的 host 与 .npmrc registry 不一致 → 失败
                     （踩过：287 个 URL 曾指向 registry.npmmirror.com，
                       海外 CI runner 拉 tarball 频繁 503，卡满 15 分钟后失败）
  LOCKFILE_VERSION   lockfileVersion 不是 3                        → 仅提示

**刻意不检查**：lock 里有节点、但磁盘上对应 workspace 不存在 —— 这是闭源
workspace 的正常形态（见上）。

用法
----
  # 在仓库根执行（自动定位 package.json 与 package-lock.json）
  python3 scripts/check-npm-lock.py

  # 指定仓库根
  python3 scripts/check-npm-lock.py --root /www/wwwroot/cenkor-admin

  # 版本范围解析不了时降级为提示而非失败（CI 保持默认严格）
  python3 scripts/check-npm-lock.py --lenient

  # 供 hook 用：通过时不输出
  python3 scripts/check-npm-lock.py --quiet

退出码：0 = 通过，1 = 有问题，2 = 用法/环境错误。
纯标准库实现，不需要 node / npm / node_modules。
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path
from typing import Any

LOCKFILE_VERSION_OK = 3

# 这些 protocol 不参与「lock 实体节点」校验：
#   workspace: 内部互相引用，npm 用软链，不产生 node_modules 实体
#   file: / link: 本地路径依赖
#   npm: / patch: 别名与补丁
_NON_REGISTRY_PROTOCOLS = ("workspace:", "file:", "link:", "portal:", "npm:", "patch:")


def read_json(path: Path) -> dict[str, Any]:
    """读 JSON。失败直接抛，调用方负责给出可读错误。"""
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def ver_tuple(text: str) -> tuple[int, int, int] | None:
    """取版本号前三位，容忍 `1.2.3-beta.1` / `v1.2.3` 这类写法。"""
    m = re.match(r"^[v=]*\s*(\d+)\.(\d+)\.(\d+)", text.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def satisfies(version: str, spec: str) -> bool | None:
    """判断 version 是否满足 spec。

    返回 True/False；返回 None 表示「这个范围写法本脚本不认识」——
    调用方据此降级为提示，避免因解析能力不足而误报失败。
    """
    spec = spec.strip()
    if spec in ("", "*", "x", "X", "latest"):
        return True
    if spec.startswith(_NON_REGISTRY_PROTOCOLS):
        return True

    cur = ver_tuple(version)
    if cur is None:
        return None

    # 精确版本（含前缀 v）
    if re.match(r"^[v=]?\d+\.\d+\.\d+", spec):
        return cur == ver_tuple(spec)

    # 多个条件用空格分隔：">=1.0.0 <2.0.0"
    if " " in spec.strip() and not spec.startswith("^") and not spec.startswith("~"):
        parts = spec.split()
        results = [satisfies(version, p) for p in parts if p]
        if any(r is None for r in results):
            return None
        return all(results)

    # 逻辑或：A || B
    if "||" in spec:
        results = [satisfies(version, p) for p in spec.split("||")]
        if any(r is True for r in results):
            return True
        if any(r is None for r in results):
            return None
        return False

    m = re.match(r"^([\^~])\s*(.+)$", spec)
    if m:
        op, rest = m.group(1), m.group(2)
        base = ver_tuple(rest)
        if base is None:
            return None
        if op == "~":
            # ~1.2.3 → 1.2.x
            return cur[0] == base[0] and cur[1] == base[1] and cur >= base
        # ^ 的语义按首个非零位切分
        if base[0] > 0:
            return cur[0] == base[0] and cur >= base
        if base[1] > 0:
            return cur[0] == 0 and cur[1] == base[1] and cur >= base
        return cur == base

    m = re.match(r"^(>=|>|<=|<)\s*(.+)$", spec)
    if m:
        op, rest = m.group(1), m.group(2)
        base = ver_tuple(rest)
        if base is None:
            return None
        return {
            ">=": cur >= base,
            ">": cur > base,
            "<=": cur <= base,
            "<": cur < base,
        }[op]

    # `1.x` / `1.2.x` 这类
    if re.match(r"^\d+(\.\d+)?\.[xX*]$|^\d+\.[xX*]$", spec):
        parts = re.split(r"[.]", spec.replace("x", "0").replace("X", "0").replace("*", "0"))
        base = ver_tuple(".".join(parts))
        if base is None:
            return None
        return cur[: len(parts)] == base[: len(parts)]

    return None


def collect_workspaces(root: Path, patterns: list[str]) -> list[tuple[str, Path, dict[str, Any]]]:
    """按 workspaces glob 找出磁盘上真实存在的 workspace。

    返回 [(lock 里的 key, 目录, package.json 内容)]，key 形如 `frontend/admin-web`。
    """
    found: list[tuple[str, Path, dict[str, Any]]] = []
    seen: set[str] = set()
    for pattern in patterns:
        for hit in sorted(glob.glob(str(root / pattern))):
            d = Path(hit)
            pkg_path = d / "package.json"
            if not d.is_dir() or not pkg_path.is_file():
                continue
            rel = d.relative_to(root).as_posix()
            if rel in seen:
                continue
            seen.add(rel)
            try:
                found.append((rel, d, read_json(pkg_path)))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"✗ {pkg_path} 不是合法 JSON：{exc}")
    return found


def all_declared_deps(pkg: dict[str, Any]) -> dict[str, str]:
    """合并四类依赖声明：运行时/开发/对等/可选。"""
    merged: dict[str, str] = {}
    for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        block = pkg.get(field)
        if isinstance(block, dict):
            for name, spec in block.items():
                if isinstance(spec, str):
                    merged.setdefault(name, spec)
    return merged


def lookup_node(packages: dict[str, Any], ws_rel: str, name: str) -> tuple[str, str] | None:
    """在 lock 里找某个依赖的实体节点，优先 workspace 内嵌套，其次根级提升。

    返回 (节点路径, 版本)。
    """
    for key in (f"{ws_rel}/node_modules/{name}", f"node_modules/{name}"):
        node = packages.get(key)
        if isinstance(node, dict) and isinstance(node.get("version"), str):
            return key, node["version"]
        # 符号链接型节点（workspace 内部包）只有 link 没有 version
        if isinstance(node, dict) and node.get("link") is True:
            return key, "(link)"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="npm workspace 与 package-lock 一致性检查",
    )
    parser.add_argument("--root", default=".", help="仓库根目录，默认当前目录")
    parser.add_argument("--lenient", action="store_true",
                        help="版本范围解析不了时降级为提示（默认失败）")
    parser.add_argument("--quiet", action="store_true", help="通过时不输出")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    pkg_path = root / "package.json"
    lock_path = root / "package-lock.json"

    if not pkg_path.is_file():
        print(f"✗ 找不到 {pkg_path}", file=sys.stderr)
        return 2
    if not lock_path.is_file():
        print(f"✗ 找不到 {lock_path}", file=sys.stderr)
        return 2

    try:
        root_pkg = read_json(pkg_path)
        lock = read_json(lock_path)
    except json.JSONDecodeError as exc:
        print(f"✗ JSON 解析失败：{exc}", file=sys.stderr)
        return 2

    packages: dict[str, Any] = lock.get("packages") or {}
    if not isinstance(packages, dict) or not packages:
        print("✗ lock 里没有 packages 节点，无法校验（lockfileVersion 1 不支持）", file=sys.stderr)
        return 2

    patterns = root_pkg.get("workspaces")
    if isinstance(patterns, dict):
        patterns = patterns.get("packages")
    if not isinstance(patterns, list) or not patterns:
        patterns = []

    on_disk = collect_workspaces(root, patterns)
    on_disk_rels = {rel for rel, _d, _p in on_disk}

    # lock 里出现的 workspace 目录（`frontend/xxx` 这类，排除 `.../node_modules/...`）
    lock_ws: list[str] = []
    for key, node in packages.items():
        if not key or "node_modules/" in key:
            continue
        if isinstance(node, dict) and ("dependencies" in node or "devDependencies" in node
                                       or "peerDependencies" in node):
            lock_ws.append(key)

    # 只在 lock 里、磁盘上没有的 workspace（闭源资产在 CI 的常态）
    lock_only = sorted(set(lock_ws) - on_disk_rels)

    missing: list[tuple[str, str, str]] = []       # (workspace, 包名, 声明范围)
    mismatched: list[tuple[str, str, str, str]] = []  # (ws, 包名, 声明, lock 实际)
    unknown: list[tuple[str, str, str, str]] = []  # 范围解析不了
    stale_decl: list[tuple[str, str, str, str]] = []  # (ws, 包名, package.json, lock)

    for ws_rel, _ws_dir, ws_pkg in on_disk:
        declared = all_declared_deps(ws_pkg)

        # ① lock 里该 workspace 的声明块，是否与 package.json 同步
        decl_node = packages.get(ws_rel)
        lock_declared: dict[str, str] = {}
        if isinstance(decl_node, dict):
            for field in ("dependencies", "devDependencies", "peerDependencies",
                          "optionalDependencies"):
                block = decl_node.get(field)
                if isinstance(block, dict):
                    for name, spec in block.items():
                        if isinstance(spec, str):
                            lock_declared.setdefault(name, spec)

        for name, spec in declared.items():
            if spec.startswith(_NON_REGISTRY_PROTOCOLS):
                continue
            if name in lock_declared and lock_declared[name] != spec:
                stale_decl.append((ws_rel, name, spec, lock_declared[name]))

        # ② 每个依赖在 lock 里必须有可解析的实体节点
        for name, spec in declared.items():
            if spec.startswith(_NON_REGISTRY_PROTOCOLS):
                continue
            hit = lookup_node(packages, ws_rel, name)
            if hit is None:
                missing.append((ws_rel, name, spec))
                continue
            _node_key, version = hit
            if version == "(link)":
                continue
            verdict = satisfies(version, spec)
            if verdict is False:
                mismatched.append((ws_rel, name, spec, version))
            elif verdict is None:
                unknown.append((ws_rel, name, spec, version))

    # ③ 仅 lock 里有的 workspace（无源码）：用 lock 自带的声明块查实体节点。
    #    这一路是 CI 唯一能用的数据源 —— 2026-11-11 那个 bug 就藏在这里。
    for ws_rel in lock_only:
        decl_node = packages.get(ws_rel)
        if not isinstance(decl_node, dict):
            continue
        lock_declared = {}
        for field in ("dependencies", "devDependencies", "peerDependencies",
                      "optionalDependencies"):
            block = decl_node.get(field)
            if isinstance(block, dict):
                for name, spec in block.items():
                    if isinstance(spec, str):
                        lock_declared.setdefault(name, spec)
        for name, spec in lock_declared.items():
            if spec.startswith(_NON_REGISTRY_PROTOCOLS):
                continue
            hit = lookup_node(packages, ws_rel, name)
            if hit is None:
                missing.append((ws_rel, name, spec))
                continue
            _node_key, version = hit
            if version == "(link)":
                continue
            verdict = satisfies(version, spec)
            if verdict is False:
                mismatched.append((ws_rel, name, spec, version))
            elif verdict is None:
                unknown.append((ws_rel, name, spec, version))

    # ③ registry 漂移：lock 里 resolved 的 host 必须与 .npmrc 一致
    registry_host = ""
    npmrc = root / ".npmrc"
    if npmrc.is_file():
        for line in npmrc.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("registry=") and not line.startswith("#"):
                registry_host = line.split("=", 1)[1].strip().rstrip("/")
                registry_host = re.sub(r"^https?://", "", registry_host)
                break

    drift_hosts: dict[str, int] = {}
    if registry_host:
        for node in packages.values():
            if not isinstance(node, dict):
                continue
            resolved = node.get("resolved")
            if not isinstance(resolved, str):
                continue
            m = re.match(r"^https?://([^/]+)/", resolved)
            if not m:
                continue
            host = m.group(1)
            if host != registry_host:
                drift_hosts[host] = drift_hosts.get(host, 0) + 1

    lockfile_version = lock.get("lockfileVersion")

    # ---------- 输出 ----------
    problems = bool(missing or mismatched or stale_decl or drift_hosts)
    if args.lenient:
        problems = bool(missing or stale_decl or drift_hosts)

    if not args.quiet or problems:
        print(f"仓库根：{root}")
        print(f"workspace：磁盘 {len(on_disk)} 个 / lock 独有 {len(lock_only)} 个"
              f"（按 {' '.join(patterns) or '(无)'} 匹配磁盘实际存在）")
        for ws_rel in sorted(on_disk_rels):
            print(f"    - {ws_rel}   [磁盘源码，全量校验]")
        for ws_rel in lock_only:
            print(f"    - {ws_rel}   [仅 lock 有声明，按 lock 声明块校验]")
        print(f"lock 节点：{len(packages)} 个，lockfileVersion={lockfile_version}")
        if registry_host:
            print(f"registry：{registry_host}（来自 .npmrc）")
        print()

        if lockfile_version != LOCKFILE_VERSION_OK:
            print(f"· LOCKFILE_VERSION = {lockfile_version}，本脚本按 3 校验；"
                  f"若是 1/2 请先升级 npm。")
            print()

        if missing:
            print(f"✗ MISSING_DEP（workspace 声明了依赖，lock 里没有实体节点）— {len(missing)} 处：")
            for ws_rel, name, spec in missing[:40]:
                print(f"    {ws_rel:<28} {name} {spec}")
            if len(missing) > 40:
                print(f"    ... 另 {len(missing) - 40} 处")
            print()
            print("  修法：在仓库根执行")
            print("      npm install --package-lock-only")
            print("  这会补齐缺失节点而不改 package.json。补完用")
            print("      git diff --stat package-lock.json")
            print("  看规模，但**别只信行数**（npm 会重排 JSON 键序）；")
            print("  要解析前后两份 lock 逐节点比，确认「删除 0 / 版本变化 0」。")
            print()

        if mismatched:
            print(f"✗ VERSION_MISMATCH（lock 版本不满足声明范围）— {len(mismatched)} 处：")
            for ws_rel, name, spec, version in mismatched[:30]:
                print(f"    {ws_rel:<28} {name}  声明 {spec}，lock 里是 {version}")
            print()
            print("  修法：确认是声明写错还是 lock 该更新，再 npm install --package-lock-only。")
            print()

        if stale_decl:
            print(f"✗ STALE_DECL（lock 里 workspace 依赖清单与 package.json 不同步）— "
                  f"{len(stale_decl)} 处：")
            for ws_rel, name, want, got in stale_decl[:30]:
                print(f"    {ws_rel:<28} {name}  package.json={want}  lock={got}")
            print()
            print("  修法：npm install --package-lock-only 让 lock 追上声明。")
            print()

        if drift_hosts:
            print(f"✗ REGISTRY_DRIFT（lock 里 resolved 的 host 与 .npmrc 不一致）— "
                  f"{sum(drift_hosts.values())} 个节点：")
            for host, count in sorted(drift_hosts.items(), key=lambda kv: -kv[1]):
                print(f"    {host:<40} {count} 个")
            print()
            print(f"  期望全部指向 {registry_host}。第三方镜像会让海外 CI runner 拉")
            print("  tarball 时频繁 503/504，并把单次安装拖到超时。")
            print("  修法：npm install --package-lock-only 重新归一 resolved URL。")
            print()

        if unknown:
            mark = "·" if args.lenient else "✗"
            print(f"{mark} UNCHECKED_RANGE（版本范围写法本脚本不认识，未能校验）— "
                  f"{len(unknown)} 处：")
            for ws_rel, name, spec, version in unknown[:20]:
                print(f"    {ws_rel:<28} {name} {spec}（lock 里是 {version}）")
            if len(unknown) > 20:
                print(f"    ... 另 {len(unknown) - 20} 处")
            if not args.lenient:
                print("  这些条目**无法自动判断**是否符合。请人工确认，或用 --lenient 降级为提示。")
            print()

    if not problems and not (unknown and not args.lenient):
        if not args.quiet:
            total_ws = len(on_disk) + len(lock_only)
            print(f"✓ lock 与 {total_ws} 个 workspace 的声明一致，"
                  f"缺失 0 / 版本不符 0 / registry 未漂移")
        return 0

    if problems:
        print("✗ npm lock 一致性检查未通过。")
        return 1

    print("✗ 存在无法自动校验的版本范围，请人工确认或用 --lenient。")
    return 1


if __name__ == "__main__":
    sys.exit(main())