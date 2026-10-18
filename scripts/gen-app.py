#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen-app.py — cenkor-admin CRUD 代码生成器（CLI 薄封装）

生成核心已抽到 ``backend/src/cenkor_admin/codegen/builder.py``，
本脚本只负责命令行参数解析、落盘、控制台输出与自检。

用法（在仓库根目录执行）：
    python3 scripts/gen-app.py --spec scripts/templates/app/spec.sample.yaml
    python3 scripts/gen-app.py --spec my.yaml --apps-dir <apps 根> --versions-dir <alembic versions>

两种模式（--mode）：
    package（默认）  迁移写进 App 自己的 alembic/versions/，随 ZIP 分发。
    builtin          平台内置 / 开源应用：迁移直接写进全局链 backend/alembic/versions/，
                     挂「开源链 head」，并把原本挂在该 head 下的闭源链入口顺延到新迁移
                     之下，保证「全量视图」与「开源视图」都仍只有唯一 head。

依赖：仅需标准库 + PyYAML（不依赖 Jinja2）。builtin 模式还需 git。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

try:
    import yaml  # noqa: F401
except ImportError:  # pragma: no cover
    print("✗ 需要 PyYAML：pip install pyyaml", file=sys.stderr)
    raise SystemExit(2)

from cenkor_admin.codegen import builder as B  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="cenkor-admin CRUD 代码生成器")
    ap.add_argument("--spec", required=True, help="spec YAML 路径")
    ap.add_argument("--apps-dir", default="backend/src/cenkor_admin/apps", help="App 输出根目录")
    ap.add_argument("--versions-dir", default="backend/alembic/versions", help="alembic versions 目录（用于取 head）")
    ap.add_argument("--templates", default=str(REPO_ROOT / "scripts" / "templates" / "app"), help="模板目录")
    ap.add_argument("--overwrite", action="store_true", help="已存在时覆盖")
    ap.add_argument("--check-import", action="store_true", help="额外尝试 import 生成的 models.py（需在 backend 目录、依赖已装）")
    ap.add_argument("--mode", choices=("package", "builtin"), default="package",
                    help="package＝迁移写进 App 自己的 alembic/versions（随 ZIP 分发）；"
                         "builtin＝平台内置/开源应用，迁移直接写进全局链并挂开源链 head")
    args = ap.parse_args()

    spec_path = Path(args.spec)
    if not spec_path.exists():
        print("✗ spec 不存在：%s" % spec_path, file=sys.stderr)
        return 2

    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    spec = B.norm_spec(raw)

    apps_dir = Path(args.apps_dir)
    versions_dir = Path(args.versions_dir)
    templates_dir = Path(args.templates)

    app_dir = apps_dir / spec["key"]
    if app_dir.exists() and not args.overwrite:
        print("✗ 目标已存在：%s（加 --overwrite 覆盖）" % app_dir, file=sys.stderr)
        return 2

    head = B.resolve_head(versions_dir, args.mode)
    if args.mode == "builtin":
        print("▸ builtin 模式：挂载点＝开源链 head：%s" % head)
    else:
        print("▸ package 模式：挂载点＝当前全量 head：%s" % head)
    print("▸ 生成 App：%s（%d 个实体）" % (spec["key"], len(spec["entities"])))

    files = B.build_files(
        raw, mode=args.mode, versions_dir=versions_dir, templates_dir=templates_dir
    )

    # 迁移在映射里的相对路径（两种模式 build_files 都产出，落盘位置不同）
    mig_rel = next(k for k in files if k.startswith("alembic/versions/"))
    mig_name = Path(mig_rel).name

    # 清理该 App 旧的生成迁移，避免同一 App 留两份（时间戳不同名）
    for old in (versions_dir if args.mode == "builtin" else app_dir / "alembic" / "versions").glob(
        "*_create_%s.py" % spec["key"]
    ):
        old.unlink()

    if args.mode == "builtin":
        # 内置模式：迁移不落在 App 目录，写入全局链
        versions_dir.mkdir(parents=True, exist_ok=True)
        (versions_dir / mig_name).write_text(files.pop(mig_rel), encoding="utf-8")

    B.write_files(files, app_dir)

    mig_disk = versions_dir / mig_name if args.mode == "builtin" else app_dir / mig_rel
    mig_rev, _down = B.parse_migration(mig_disk)
    print("▸ 迁移：%s（revision=%s, down_revision=%s）" % (mig_disk, mig_rev, head))
    if args.mode == "builtin":
        # 把原本挂在开源链旧 head 下的闭源链入口顺延到新迁移之下，保证全量视图仍唯一 head
        for fname, new_down in B.rebase_closed_chain(
            versions_dir, old_head=head, new_rev=mig_rev, exclude={mig_name}
        ):
            print("▸ 闭源链顺延：%s 的 down_revision → %s" % (fname, new_down))

    print("▸ 生成完成：%s" % app_dir)
    if args.mode == "builtin":
        print("▸ builtin 模式：迁移已在全局链，请随 App 源码一并 git 跟踪提交（无需写入 .gitignore）")
    else:
        print("▸ 打包命令：bash scripts/package-app.sh %s %s" % (spec["key"], spec["version"]))

    # 自检
    problems = B.self_check(spec, files, versions_dir=versions_dir, mode=args.mode)
    if problems:
        print("\n✗ 自检未通过：")
        for p in problems:
            print("    - %s" % p)
        return 1
    scope = "全量 + 开源视图均唯一 head" if args.mode == "builtin" else "迁移仍唯一 head"
    print("\n✓ 自检通过：包结构完整、语法可编译、菜单/路由一致、%s" % scope)

    if args.check_import:
        import subprocess

        code = ("import importlib;"
                "importlib.import_module('cenkor_admin.apps.%s.models');"
                "print('  ✓ import models OK')" % spec["key"])
        env = dict(os.environ, PYTHONPATH="src")
        r = subprocess.run([sys.executable, "-c", code], cwd=str(apps_dir.parent.parent.parent.parent),
                           env=env, capture_output=True, text=True)
        if r.returncode == 0:
            print(r.stdout.strip())
        else:
            print("  ✗ import 检查失败：%s" % (r.stderr.strip().splitlines()[-1] if r.stderr else r.returncode))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
