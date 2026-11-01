#!/usr/bin/env python3
"""文档事实校验：把 md 里出现的表名 / 前端路由 / 后端 API 前缀对代码和数据库核一遍。

用法（在仓库根执行）：

    python3 scripts/check-doc-facts.py          # 只报告
    python3 scripts/check-doc-facts.py --strict # 有错就 exit 1（接 CI 用）

校验范围：architecture.md、admin_system_comparison.md、docs/*.md、
docs/apps/*.md、docs/05-用户手册/*.md。
归档与「本机未采用」的部署方案（archive / baota_static_deploy / native_deploy /
fullstack_deploy / roadmap）不校验 —— 它们本来是历史或备选路径。

只做**硬校验**（名字写错、路径不存在）。语义层面的过时（比如「选了 Liquid」
而实际选了 Jinja2）脚本看不出来，得靠人读。

数据库连接默认读环境变量 PGHOST/PGUSER/PGDATABASE/PGPASSWORD，
缺省按本机生产配置（127.0.0.1 / cenkor / cenkor）。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PG = os.environ.get("PSQL_BIN") or "/www/server/pgsql/bin/psql"

MD_TARGETS = [
    REPO / "architecture.md",
    REPO / "admin_system_comparison.md",
    *sorted((REPO / "docs").glob("*.md")),
    *sorted((REPO / "docs" / "apps").glob("*.md")),
    *sorted((REPO / "docs" / "05-用户手册").glob("*.md")),
]

# 历史文档 / 本机未采用的方案 / 竞品对比（含"建议新增表"），不参与校验
SKIP_STEMS = {
    "archive",
    "baota_static_deploy",
    "native_deploy",
    "fullstack_deploy",
    "roadmap",
    "admin_system_comparison",
}

# 代码标识符、MCP 工具名、列名等，不是表名
NOT_TABLES = {"portal_payload", "portal_token", "cms_page_router"}

# 文档示例里虚构的 App key / 占位符：它们的存在意义就是「教你怎么写」，
# 代码里当然找不到对应前缀，不算硬错误。
EXAMPLE_SEGMENTS = {"my_app", "myapp", "my-app", "{key}", "{app_key}", "example", "your_app"}
NOT_TABLE_PREFIX = re.compile(r"^cms_(create|update|get|list|search|publish|translate|describe|ai_draft)_")
NOT_TABLE_SUFFIX = ("_models", "_tables", "_page", "_model", "_id", "_bp")


def psql_tables() -> set[str]:
    env = {
        **os.environ,
        "PGHOST": os.environ.get("PGHOST", "127.0.0.1"),
        "PGUSER": os.environ.get("PGUSER", "cenkor"),
        "PGDATABASE": os.environ.get("PGDATABASE", "cenkor"),
        "PGPASSWORD": os.environ.get("PGPASSWORD", ""),
    }
    sql = "select table_name from information_schema.tables where table_schema='public'"
    try:
        r = subprocess.run([PG, "-At", "-c", sql], capture_output=True, text=True, env=env, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"⚠️  连不上数据库，跳过表名校验：{exc}", file=sys.stderr)
        return set()
    if r.returncode != 0:
        print(f"⚠️  psql 失败，跳过表名校验：{r.stderr.strip()[:200]}", file=sys.stderr)
        return set()
    return {line.strip() for line in r.stdout.splitlines() if line.strip()}


def frontend_routes() -> set[str]:
    router = REPO / "frontend/admin-web/src/router/index.ts"
    if not router.exists():
        return set()
    text = router.read_text(encoding="utf-8")
    out = set()
    for raw in re.findall(r"path:\s*'([^']+)'", text):
        p = raw.strip()
        if not p or p == "/":
            continue
        out.add(("/" + p.lstrip("/")).rstrip("/"))
    return out


def backend_source() -> str:
    root = REPO / "backend/src/cenkor_admin"
    if not root.exists():
        return ""
    return "\n".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in root.rglob("*.py")
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="发现问题时以非零码退出")
    args = ap.parse_args()

    files = [f for f in MD_TARGETS if f.exists() and f.stem not in SKIP_STEMS]
    tables = psql_tables()
    routes = frontend_routes()
    src = backend_source()

    problems: list[tuple[str, str, str]] = []

    for f in files:
        rel = str(f.relative_to(REPO))
        text = f.read_text(encoding="utf-8")

        if tables:
            for t in set(re.findall(r"\b((?:cms|portal|platform|auth)_[a-z0-9_]+)\b", text)):
                if t in tables or t.endswith("_") or t in NOT_TABLES:
                    continue
                if NOT_TABLE_PREFIX.match(t) or t.endswith(NOT_TABLE_SUFFIX):
                    continue
                problems.append((rel, "表名不存在", t))

        if routes:
            for p in set(re.findall(r"[`'\"](/cms/[a-z0-9\-/]+)[`'\"]", text)):
                if p.rstrip("/") not in routes:
                    problems.append((rel, "前端路由不存在", p))

        if src:
            for p in set(re.findall(r"[`'\"](/api/v1/[A-Za-z0-9_\-/{}*]{2,})[`'\"]", text)):
                seg = p.replace("/api/v1", "").strip("/").split("/")[0]
                if seg in EXAMPLE_SEGMENTS:
                    continue
                if seg and seg not in src:
                    problems.append((rel, "API 前缀在代码里找不到", p))

    print(f"校验文件 {len(files)} 份 · 表 {len(tables)} 张 · 前端路由 {len(routes)} 条\n")
    if not problems:
        print("✅ 未发现硬错误")
        return 0

    grouped: dict[str, set[tuple[str, str]]] = {}
    for rel, kind, val in problems:
        grouped.setdefault(kind, set()).add((val, rel))

    for kind, items in grouped.items():
        print(f"❌ {kind}（{len(items)}）")
        for val, rel in sorted(items):
            print(f"   {val:45s} ← {rel}")
        print()

    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
