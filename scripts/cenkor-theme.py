#!/usr/bin/env python3
"""cenkor-theme —— 主题开发者命令行工具。

    cenkor-theme init my-blog --from blog    生成可跑的骨架
    cenkor-theme lint ./my-blog              校验清单 + 语法 + CSP
    cenkor-theme pack ./my-blog              打出 dist/my-blog-1.0.0.zip
    cenkor-theme list                        列出可用的内置样板

## 为什么要 CLI

后台「模板工作台」已经能改模板，但它解决不了三件事：

1. **没有版本管理** —— 写坏了回不去，也没法 diff
2. **没有本地 IDE** —— 一个 CodeMirror 输入框写不了几百行 CSS
3. **没法分发** —— 导出的是内部 zip（无清单、无版本、无设置项声明）

CLI 就是补这三件事。产物是一个标准 zip，能直接拖进后台「导入」，
将来也能直接提交到商店。

## 两条校验路径

找到后端源码时，用 ``theme_package`` + ``jinja_env`` 做**真校验**（编译模板、
跑沙箱、查内联脚本）。找不到时降级成基础校验（JSON 结构 + 路径白名单 +
扫 ``<script>`` 字样），并在报告里明确说"降级了"—— 不能让人以为过了就是过了。

降级路径不是偷懒：外部开发者可能只拿到一个 zip 和一个 CLI，
不能要求他先装一整套 Python 后端依赖才能 lint 自己的主题。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

TOOL_VERSION = "1.0.0"

# 会被跳过、不进包的东西
SKIP_DIRS = {".git", ".idea", ".vscode", "__pycache__", "node_modules", "dist", ".venv", "venv"}
SKIP_FILES = {".DS_Store", "Thumbs.db", ".gitignore"}

# 单文件 / 总量上限，与 theme_package 保持一致（降级路径也得守）
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 5 * 1024 * 1024
MAX_FILES = 300

_NAME_RE = re.compile(r"^[A-Za-z0-9_\-./]+\.(?:html|xml|txt|json|css|js)$")
_CSP_BAD = [
    (re.compile(r"<script(?![^>]*type\s*=\s*[\"'](?:application/ld\+json|text/template)[\"'])", re.I),
     "内联 <script>（除 ld+json / text-template）会被严格 CSP 拦掉，脚本请用 {{ script('assets/x.js') }}"),
    (re.compile(r"\son[a-z]+\s*=\s*[\"']", re.I), "内联事件属性（onclick 等）会被严格 CSP 拦掉"),
    (re.compile(r"javascript\s*:", re.I), "javascript: 伪协议会被严格 CSP 拦掉"),
]


# ---------------------------------------------------------------- 输出


class C:
    G = "\033[32m"
    R = "\033[31m"
    Y = "\033[33m"
    B = "\033[36m"
    DIM = "\033[2m"
    OFF = "\033[0m"


def _tty() -> bool:
    return sys.stdout.isatty()


def say(msg: str = "", color: str = "") -> None:
    print(f"{color}{msg}{C.OFF}" if color and _tty() else msg)


def ok(msg: str) -> None:
    say(f"  ✓ {msg}", C.G)


def err(msg: str) -> None:
    say(f"  ✗ {msg}", C.R)


def warn(msg: str) -> None:
    say(f"  ! {msg}", C.Y)


def head(msg: str) -> None:
    say(f"\n{msg}", C.B)


# ---------------------------------------------------------------- 后端探测


def bootstrap_backend(explicit: str | None = None) -> bool:
    """把 cenkor_admin 加进 sys.path。成功返回 True（真校验），失败 False（降级）。"""
    cands: list[Path] = []
    if explicit:
        p = Path(explicit).expanduser().resolve()
        cands.append(p / "src" if (p / "src" / "cenkor_admin").is_dir() else p)
    here = Path(__file__).resolve()
    for up in (here.parent, here.parent.parent, here.parent.parent.parent):
        cands.append(up / "backend" / "src")
        cands.append(up / "src")
    cands.append(Path.cwd() / "backend" / "src")
    cands.append(Path.cwd() / "src")

    for c in cands:
        if (c / "cenkor_admin" / "apps" / "cms" / "theme_package.py").is_file():
            if str(c) not in sys.path:
                sys.path.insert(0, str(c))
            try:
                import cenkor_admin.apps.cms.theme_package  # noqa: F401
                return True
            except Exception:
                continue
    return False


# ---------------------------------------------------------------- lint


def walk_theme(root: Path) -> tuple[dict[str, str], list[str]]:
    """读主题目录里的所有文本文件。返回 (相对路径→内容, 被跳过的非文本文件)。"""
    files: dict[str, str] = {}
    skipped: list[str] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if any(part in SKIP_DIRS for part in rel.split("/")):
            continue
        if p.name in SKIP_FILES:
            continue
        # .md 不收：README / CHANGELOG 是给人看的，沙箱和包体都不认这个扩展名
        if p.suffix.lower() not in (".html", ".xml", ".css", ".js", ".json", ".txt"):
            skipped.append(rel)
            continue
        try:
            files[rel] = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            skipped.append(rel)
    return files, skipped


def lint(root: Path, *, use_backend: bool) -> int:
    """返回退出码：0 通过，1 有错。"""
    if not root.is_dir():
        err(f"目录不存在：{root}")
        return 1

    say(f"检查主题目录：{root}")

    files, skipped = walk_theme(root)
    if not files:
        err("目录里没有可打包的文本文件")
        return 1
    if skipped:
        warn(f"跳过 {len(skipped)} 个非文本文件（主题包只收 html/xml/css/js/json）：{skipped[:5]}")

    errors: list[str] = []
    warns: list[str] = []

    # ---- 体积闸
    total = sum(len(v.encode()) for v in files.values())
    if len(files) > MAX_FILES:
        errors.append(f"文件数 {len(files)} 超过上限 {MAX_FILES}")
    if total > MAX_TOTAL_BYTES:
        errors.append(f"总体积 {total / 1024 / 1024:.1f}MB 超过上限 {MAX_TOTAL_BYTES // 1024 // 1024}MB")
    for name, content in files.items():
        if len(content.encode()) > MAX_FILE_BYTES:
            errors.append(f"{name} 超过单文件 {MAX_FILE_BYTES // 1024}KB")

    # ---- 清单
    if "theme.json" not in files:
        errors.append("缺 theme.json —— 没有清单就没法声明版本、作者和可配置项")
    else:
        try:
            json.loads(files["theme.json"])
        except json.JSONDecodeError as e:
            errors.append(f"theme.json 不是合法 JSON：{e}")

    # ---- 路径
    for name in files:
        if not _NAME_RE.match(name) or ".." in name or name.startswith("/"):
            errors.append(f"{name} 路径非法或扩展名不在白名单")
        if any(seg.startswith("_") for seg in name.split("/")):
            errors.append(f"{name} 有下划线开头的路径段（会被沙箱拒绝）")

    if use_backend:
        rc_errors, rc_warns = _lint_with_backend(files)
    else:
        rc_errors, rc_warns = _lint_degraded(files)

    errors.extend(rc_errors)
    warns.extend(rc_warns)

    head("结果")
    for w in warns:
        warn(w)
    if errors:
        for e in errors:
            err(e)
        say(f"\n{len(errors)} 个错误，{len(warns)} 个警告", C.R)
        return 1
    ok(f"{len(files)} 个文件通过，{len(warns)} 个警告")
    return 0


def _lint_with_backend(files: dict[str, str]) -> tuple[list[str], list[str]]:
    """真校验：走后台同一套 theme_package + jinja_env。"""
    from cenkor_admin.apps.cms import theme_package

    check = theme_package.validate_package(dict(files), require_manifest=True)
    errors = [f"{e.get('path', '')} {e.get('message', '')}".strip() for e in check.errors]
    warns = [f"{w.get('path', '')} {w.get('message', '')}".strip() for w in check.warnings]
    if check.ok:
        m = check.manifest
        if m:
            say(f"  清单：{m.name} v{m.version}，{len(m.settings)} 个配置项，"
                f"声明资源 {list(m.asset_kinds) or ['css（默认）']}")
    return errors, warns


def _lint_degraded(files: dict[str, str]) -> tuple[list[str], list[str]]:
    """降级校验：不编译 Jinja，只做静态扫描。"""
    errors: list[str] = []
    warns: list[str] = [
        "没有找到后端源码，本次只做了静态扫描（模板语法、沙箱边界都没验）",
        "要完整校验：加 --backend /path/to/cenkor-admin/backend",
    ]

    declared: set[str] = set()
    if "theme.json" in files:
        try:
            manifest = json.loads(files["theme.json"])
            declared = set((manifest.get("requires") or {}).get("asset_kinds") or [])
        except Exception:
            pass

    present: set[str] = set()
    for name, content in files.items():
        if name.endswith(".css"):
            present.add("css")
        elif name.endswith(".js"):
            present.add("js")
        if name.endswith((".html", ".xml")):
            for pattern, msg in _CSP_BAD:
                m = pattern.search(content)
                if m:
                    line = content[: m.start()].count("\n") + 1
                    errors.append(f"{name}:{line} {msg}")

    undeclared = present - declared
    if undeclared and "theme.json" in files:
        errors.append(f"带了 {sorted(undeclared)} 文件但 requires.asset_kinds 没声明")
    return errors, warns


# ---------------------------------------------------------------- init


def cmd_init(args: argparse.Namespace) -> int:
    key = args.key.strip()
    if not re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", key):
        err("主题 key 只能用小写字母、数字、连字符、下划线，1-64 位")
        return 1

    dest = Path(args.dest or key).resolve()
    if dest.exists() and any(dest.iterdir()):
        err(f"目标目录非空：{dest}")
        return 1

    base = args.base or "default"
    if not bootstrap_backend(args.backend):
        err("找不到后端源码，没法读取内置主题。用 --backend 指定 backend 目录")
        return 1

    from cenkor_admin.apps.cms import builtin_theme

    if base not in builtin_theme.BUILTIN_THEMES:
        err(f"内置主题里没有 {base}，可选：{', '.join(builtin_theme.list_builtin_themes())}")
        return 1

    # 拷的是**合并后**的完整文件表，不是差异包 —— 开发者拿到手要能直接跑
    docs: dict[str, str] = dict(builtin_theme.BUILTIN_THEMES["default"])
    docs.update(builtin_theme.BUILTIN_THEMES[base])
    docs.pop("theme.json", None)

    dest.mkdir(parents=True, exist_ok=True)
    for rel, content in docs.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    # 清单按新 key 重写，保留基线的设置项（那是这份骨架的"可改点"）
    manifest = {
        "schema_version": 1,
        "key": key,
        "name": args.name or key.replace("-", " ").title().replace(" ", " "),
        "version": "0.1.0",
        "description": f"基于内置 {base} 主题的主题",
        "author": {"name": args.author or "你的名字", "url": ""},
        "license": args.license,
        "icon": "",
        "tags": [base],
        "requires": {"core_version": ">=0.5.16", "asset_kinds": ["css"]},
        "settings": _base_settings(base),
        "changelog": "0.1.0 从内置主题初始化",
        "files": sorted(docs),
    }
    (dest / "theme.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    (dest / "README.md").write_text(_readme(key, base), encoding="utf-8")

    head("完成")
    ok(f"已生成 {len(docs)} 个文件 + theme.json + README.md → {dest}")
    say(
        f"\n下一步：\n"
        f"  cd {dest.name}\n"
        f"  cenkor-theme lint .        # 改完先自检\n"
        f"  cenkor-theme pack .        # 打成 zip\n"
        f"\n然后在后台「模板工作台 → 导入 zip」装上，主题名填 {key}。",
        C.DIM,
    )
    return 0


def _base_settings(base: str) -> list[dict[str, Any]]:
    from cenkor_admin.apps.cms import builtin_theme

    m = builtin_theme.get_theme_manifest(base)
    return [s.as_dict() for s in m.settings] if m else []


def _readme(key: str, base: str) -> str:
    return f"""# {key}

基于内置 `{base}` 主题。改完打包上传即可。

## 常用命令

```bash
cenkor-theme lint .     # 校验清单 + 模板语法 + CSP 规则
cenkor-theme pack .     # 生成 dist/{key}-<version>.zip
```

## 能改什么

| 文件 | 作用 |
|---|---|
| `theme.json` | 清单：名称、版本、作者、依赖、可配置项 |
| `layout.html` | 页面骨架，其它页 `{{% extends "layout.html" %}}` |
| `list.html` | 列表页（首页 / 分类 / 标签 / 搜索） |
| `detail.html` | 详情页 |
| `page.html` | 自定义页（关于我们等） |
| `404.html` | 404 页 |
| `partials/*.html` | 页头、页脚、卡片、分页等片段 |
| `macros/ui.html` | 可复用宏 |
| `assets/style.css` | 样式（会用 `<style>` 内联，不额外请求） |
| `assets/*.js` | 脚本（必须用 `{{{{ script('assets/app.js') }}}} `引入） |

## 两条硬规则

**1. 不能写内联脚本。** 公开页跑严格 CSP（`script-src 'self'`），
`<script>…</script>`、`onclick=`、`javascript:` 全部会被拦掉 —— 而且
`lint` 和后台导入都会在提交前就报错，不会等到上线白屏。

外链脚本这样写：

```jinja
{{{{ script('assets/app.js') }}}}
```

**2. 设置项通过 CSS 变量生效。** 样式表是纯 CSS、不经过 Jinja 渲染，
所以在 `layout.html` 里覆盖变量：

```jinja
<style>:root{{{{--brand: {{{{ theme.brand_color }}}}}}}}</style>
```

模板里能用的数据 API 见后台「模板工作台 → 标签速查」。
"""


# ---------------------------------------------------------------- pack


def cmd_pack(args: argparse.Namespace) -> int:
    root = Path(args.dir).resolve()
    if not (root / "theme.json").is_file():
        err(f"{root} 里没有 theme.json")
        return 1

    code = lint(root, use_backend=bootstrap_backend(args.backend))
    if code != 0 and not args.force:
        say("\n校验没通过，已中止打包（加 --force 可强行打包，不建议）", C.R)
        return 1

    manifest = json.loads((root / "theme.json").read_text(encoding="utf-8"))
    key = str(manifest.get("key") or "").strip()
    version = str(manifest.get("version") or "0.0.0").strip()
    if not key:
        err("theme.json 里没有 key")
        return 1

    files, _skipped = walk_theme(root)

    out_dir = Path(args.out) if args.out else root / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{key}-{version}.zip"

    # 每次都重建，避免上次的残留混进来
    if target.exists():
        target.unlink()

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        # theme.json 放第一个：解压出来第一眼就该看到清单
        zf.writestr("theme.json", files.pop("theme.json"))
        for rel in sorted(files):
            zf.writestr(rel, files[rel])

    size = target.stat().st_size
    head("打包完成")
    ok(f"{target}")
    say(f"  {len(files) + 1} 个文件，{size / 1024:.1f} KB", C.DIM)
    say(
        "\n装法：后台 → 模板工作台 → 导入 zip（主题名填 "
        f"{key}），或解压到 backend/var/themes/{key}/",
        C.DIM,
    )
    return 0


# ---------------------------------------------------------------- list


def cmd_list(args: argparse.Namespace) -> int:
    if not bootstrap_backend(args.backend):
        err("找不到后端源码，没法列出内置主题。用 --backend 指定 backend 目录")
        return 1

    from cenkor_admin.apps.cms import builtin_theme

    head("内置样板主题")
    for key in builtin_theme.list_builtin_themes():
        m = builtin_theme.get_theme_manifest(key)
        n = len(builtin_theme.BUILTIN_THEMES.get(key, {}))
        if m is None:
            say(f"  {key:12} {n} 个文件")
            continue
        say(f"  {key:12} {m.name:22} v{m.version:8} {n:2} 个自有文件  {m.description[:36]}")
    say("\n用 cenkor-theme init <key> --from <上面某个> 生成骨架", C.DIM)
    return 0


# ---------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="cenkor-theme",
        description="Cenkor 主题开发工具：init / lint / pack / list",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--version", action="version", version=f"cenkor-theme {TOOL_VERSION}")
    sub = ap.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="生成主题骨架")
    p_init.add_argument("key", help="主题 key（小写字母数字连字符）")
    p_init.add_argument("--from", dest="base", default="default", help="基于哪个内置主题（默认 default）")
    p_init.add_argument("--dest", help="输出目录（默认 ./<key>）")
    p_init.add_argument("--name", help="显示名称")
    p_init.add_argument("--author", help="作者名")
    p_init.add_argument("--license", default="MIT")
    p_init.add_argument("--backend", help="后端源码目录（自动探测失败时用）")

    p_lint = sub.add_parser("lint", help="校验主题目录")
    p_lint.add_argument("dir", nargs="?", default=".", help="主题目录（默认当前目录）")
    p_lint.add_argument("--backend", help="后端源码目录（自动探测失败时用）")

    p_pack = sub.add_parser("pack", help="打包成 zip")
    p_pack.add_argument("dir", nargs="?", default=".", help="主题目录（默认当前目录）")
    p_pack.add_argument("-o", "--out", help="输出目录（默认 <dir>/dist）")
    p_pack.add_argument("--force", action="store_true", help="校验失败也打包")
    p_pack.add_argument("--backend", help="后端源码目录")

    p_list = sub.add_parser("list", help="列出内置样板")
    p_list.add_argument("--backend", help="后端源码目录")

    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 0

    return {
        "init": cmd_init,
        "lint": lambda a: lint(Path(a.dir).resolve(), use_backend=bootstrap_backend(a.backend)),
        "pack": cmd_pack,
        "list": cmd_list,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
