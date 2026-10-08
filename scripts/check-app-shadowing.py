#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""App 目录遮蔽自检 —— 防止「改了源码但不生效」。

背景
----
应用可以放在两处，导入路径都是 ``cenkor_admin.apps.<key>``：

  · 内置  backend/src/cenkor_admin/apps/<key>/   （随底座发布 / 商店安装落盘处）
  · 外置  backend/src/apps/<key>/               （独立 / 商业应用源码）

``cenkor_admin/apps/__init__.py`` 把外置目录 **追加** 到包的 ``__path__`` 末尾，
Python 找子模块时按顺序取第一个命中，所以【内置赢】。一旦同一个 key 在两处都有
目录，外置那份维护中的源码就被静默遮蔽：编辑它不会生效，运行时拿到的是内置副本。

踩过的实例（2026-10-08）：payment 1.0.0 从商店包装进内置目录，把外置
``src/apps/payment/`` 里新增的 ``detect_terminal`` 终端选路压住，
commerce 下单接口直接 AttributeError → 收银台 500。

修法：把不该存在的那一份改名或移除（保留权威源码那份）。
注意商店安装入口已有同款拦截（store_router._guard_against_shadowed_source），
本脚本兜住「手工放目录」和「存量漂移」。

用法
----
  python3 scripts/check-app-shadowing.py           # 列出冲突
  python3 scripts/check-app-shadowing.py --quiet   # 正常时不输出（供 hook / CI 用）

退出码：0 = 无遮蔽，1 = 有遮蔽。
已挂到 .githooks/pre-commit（启用：git config core.hooksPath .githooks）。
"""
from __future__ import annotations

import argparse
import os
import sys

BUILTIN_DIR = "backend/src/cenkor_admin/apps"
EXTERNAL_DIR = "backend/src/apps"


def _app_dirs(base):
    """列出目录下的应用名（含 __init__.py 或 manifest.py 的子目录）。"""
    if not os.path.isdir(base):
        return {}
    found = {}
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name)
        if name.startswith("_") or not os.path.isdir(path):
            continue
        found[name] = path
    return found


def main():
    ap = argparse.ArgumentParser(description="App 目录遮蔽自检")
    ap.add_argument("--builtin", default=BUILTIN_DIR, help="内置应用目录")
    ap.add_argument("--external", default=EXTERNAL_DIR, help="外置应用目录")
    ap.add_argument("--quiet", action="store_true", help="无冲突时不输出")
    args = ap.parse_args()

    builtin = _app_dirs(args.builtin)
    external = _app_dirs(args.external)
    clashes = sorted(set(builtin) & set(external))

    if not clashes:
        if not args.quiet:
            print("✓ 无遮蔽：内置 %d 个应用，外置 %d 个应用，同名 0 个" % (len(builtin), len(external)))
        return 0

    print("✗ 同名应用在两处同时存在 —— 内置副本会遮蔽外置源码（改外置不生效）：")
    for key in clashes:
        print("    - %s" % key)
        print("        内置（实际加载）: %s" % builtin[key])
        print("        外置（被遮蔽）  : %s" % external[key])
    print()
    print("  修法：保留权威源码那一份，把另一份改名或移除；")
    print("        若内置这份是商店安装产生的陈旧副本，移走后需重启后端。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
