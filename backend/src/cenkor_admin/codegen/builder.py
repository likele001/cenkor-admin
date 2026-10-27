"""builder.py — cenkor-admin CRUD 代码生成核心库

从 ``scripts/gen-app.py`` 抽出的纯逻辑层，供两处调用：

    · scripts/gen-app.py            —— 命令行薄封装（本地开发 / 平台内置应用）
    · apps/system/codegen_router.py —— 后台「系统 > 代码生成」页（预览 / 下载 / 安装）

对外接口：
    norm_spec(raw)                     spec 规范化 + 校验（非法时 raise SystemExit）
    build_files(raw, mode, ...)        生成全部文件，返回 {相对路径: 文本}，**不落盘**
    zip_bytes(files)                   把文件映射打成 ZIP 的 bytes
    write_files(files, out_dir)        把文件映射写到磁盘（CLI 用）
    self_check(spec, files, ...)       静态自检，返回问题列表
    current_head / tracked_head        迁移链 head 探测
    rebase_closed_chain                内置模式：顺延闭源链入口

设计原则：只依赖标准库 + PyYAML，不 import fastapi/sqlalchemy/后端任何模块，
因此可脱离后端环境独立运行与单测。错误统一用 SystemExit（API 层捕获转 400）。
"""
from __future__ import annotations

import ast
import io
import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATES_DIR = PACKAGE_DIR / "templates" / "app"
ASSETS_DIR = PACKAGE_DIR / "assets"
PLUGIN_HEAD_NAME = "plugin_head.js"

FIELD_TYPES = {"string", "text", "int", "decimal", "bool", "date", "datetime", "enum", "fk", "json"}

SA_TYPES = {
    "string": "String", "text": "Text", "int": "Integer", "decimal": "Numeric",
    "bool": "Boolean", "date": "Date", "datetime": "DateTime", "enum": "String",
    "fk": "Integer", "json": "JSONB",
}
PY_TYPES = {
    "string": "str", "text": "str", "int": "int", "decimal": "float", "bool": "bool",
    "date": "date", "datetime": "datetime", "enum": "str", "fk": "int", "json": "dict",
}


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def pascal(s: str) -> str:
    """"warehouse_cell" / "warehouse-cell" → "WarehouseCell" """
    parts = re.split(r"[_\-\s]+", s.strip())
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def camel(s: str) -> str:
    parts = re.split(r"[_\-\s]+", s.strip())
    if not parts:
        return ""
    out = parts[0][:1].lower() + parts[0][1:]
    for p in parts[1:]:
        out += p[:1].upper() + p[1:]
    return out


def snake(s: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()


def eprint(*a):
    print(*a, file=sys.stderr)


# ---------------------------------------------------------------------------
# 迁移图：读取当前唯一 head（AST 解析，不 import、不连库）
# ---------------------------------------------------------------------------

def parse_migration(path: Path):
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except SyntaxError:
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
                rev = _safe_literal(value); found = True
            elif target.id == "down_revision":
                down = _safe_literal(value)
    if not found:
        return None, None
    return rev, down


def _safe_literal(node):
    try:
        if node is None:
            return None
        return ast.literal_eval(node)
    except Exception:
        return None


def _compute_head(files: list[Path], scope: str) -> str:
    revs = {}
    downs = {}
    for f in files:
        if f.name.startswith("__"):
            continue
        rev, down = parse_migration(f)
        if rev is None:
            eprint(f"  ! 跳过（无 revision）：{f.name}")
            continue
        revs[rev] = f.name
        if down is None:
            downs[rev] = []
        elif isinstance(down, (list, tuple)):
            downs[rev] = list(down)
        else:
            downs[rev] = [down]
    referenced = {p for ps in downs.values() for p in ps}
    heads = sorted(r for r in revs if r not in referenced)
    if len(heads) == 0:
        raise SystemExit(f"✗ {scope}迁移图没有 head（全是环或全断）")
    if len(heads) > 1:
        raise SystemExit(
            "✗ %s迁移图有 %d 个 head，无法确定 down_revision：\n    %s\n"
            "  先修链为唯一 head（参考 scripts/check-migration-graph.py）再生成。"
            % (scope, len(heads), "\n    ".join(heads))
        )
    return heads[0]


def all_migration_files(versions_dir: Path) -> list[Path]:
    if not versions_dir.is_dir():
        raise SystemExit(f"✗ 迁移目录不存在：{versions_dir}")
    return sorted(f for f in versions_dir.glob("*.py"))


def git_tracked_names(versions_dir: Path) -> set[str] | None:
    """git 跟踪的迁移文件名集合（= 公开仓库视图）；无 git 时返回 None。"""
    try:
        out = subprocess.run(
            ["git", "ls-files", str(versions_dir)],
            capture_output=True, text=True, check=False,
        ).stdout
    except FileNotFoundError:
        return None
    return {os.path.basename(p) for p in out.splitlines() if p.endswith(".py")}


def current_head(versions_dir: Path) -> str:
    """全量视图 head（工作区所有迁移，含被 .gitignore 排除的闭源迁移）。"""
    return _compute_head(all_migration_files(versions_dir), "全量")


def tracked_head(versions_dir: Path) -> str:
    """开源链 head（公开仓库视图：只含 git 跟踪的迁移）。

    内置（平台自带、开源）App 的迁移绝不能挂在闭源迁移之下 —— 闭源迁移被 .gitignore
    排除后，该开源迁移在公开仓库里就成了孤儿/revision 缺失。「一键部署」会因此失败。
    故内置模式的挂载点取「开源链 head」，原本挂在它下面的闭源链入口顺延（见
    rebase_closed_chain）。
    """
    tracked = git_tracked_names(versions_dir)
    if tracked is None:
        raise SystemExit("✗ 内置模式需要 git 来识别开源链 head，但未找到 git 命令")
    files = [f for f in all_migration_files(versions_dir) if f.name in tracked]
    if not files:
        raise SystemExit(
            f"✗ 取不到 git 跟踪的迁移（{versions_dir} 未纳入版本控制？请在仓库根目录执行本脚本）"
        )
    return _compute_head(files, "开源")


# ---------------------------------------------------------------------------
# spec 解析 / 校验
# ---------------------------------------------------------------------------

def norm_field(raw: dict, entity_key: str) -> dict:
    if not raw.get("name"):
        raise SystemExit(f"✗ 字段缺少 name：{raw!r}（实体 {entity_key}）")
    f = dict(raw)
    f["name"] = str(f["name"])
    ftype = str(f.get("type", "string"))
    if ftype not in FIELD_TYPES:
        raise SystemExit("✗ 未知字段类型 {!r}（字段 {}.{}）；可用：{}".format(ftype, entity_key, f["name"], ", ".join(sorted(FIELD_TYPES))))
    f["type"] = ftype
    f["label"] = str(f.get("label") or f["name"])
    f["required"] = bool(f.get("required", False))
    f["unique"] = bool(f.get("unique", False))
    f["index"] = bool(f.get("index", False))
    f["list"] = bool(f.get("list", True))
    f["search"] = bool(f.get("search", False))
    f["filter"] = bool(f.get("filter", False))
    f["len"] = int(f.get("len") or (255 if ftype == "string" else 32))
    if ftype == "enum":
        choices = f.get("choices") or []
        if not choices:
            raise SystemExit("✗ enum 字段 {}.{} 缺少 choices".format(entity_key, f["name"]))
        f["choices"] = [str(c) for c in choices]
    if ftype == "decimal":
        f["precision"] = int(f.get("precision") or 12)
        f["scale"] = int(f.get("scale") or 2)
    if ftype == "fk":
        f["fk_entity"] = f.get("entity") or f.get("fk") or ""
    return f


def norm_spec(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise SystemExit("✗ spec 必须是一个映射（YAML 根节点为 key/value）")
    key = str(raw.get("key") or "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
        raise SystemExit(f"✗ key 必须是小写字母开头、仅含小写字母数字下划线：{key!r}")
    entities = raw.get("entities") or []
    if not entities:
        raise SystemExit("✗ spec 至少需要一个 entity")
    out = {
        "key": key,
        "name": str(raw.get("name") or pascal(key)),
        "version": str(raw.get("version") or "1.0.0"),
        "icon": str(raw.get("icon") or "📦"),
        "category": str(raw.get("category") or "business"),
        "author": str(raw.get("author") or "Cenkor Team"),
        "description": str(raw.get("description") or ""),
        "sort": int(raw.get("sort") or 80),
        "entities": [],
    }
    seen = set()
    for i, ent in enumerate(entities):
        ekey = str(ent.get("key") or "").strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", ekey):
            raise SystemExit(f"✗ entity.key 非法：{ekey!r}")
        if ekey in seen:
            raise SystemExit(f"✗ entity.key 重复：{ekey!r}")
        seen.add(ekey)
        fields = [norm_field(f, ekey) for f in (ent.get("fields") or [])]
        if not fields:
            raise SystemExit(f"✗ entity {ekey} 没有任何字段")
        if len({f["name"] for f in fields}) != len(fields):
            raise SystemExit(f"✗ entity {ekey} 字段名重复")
        out["entities"].append({
            "key": ekey,
            "name": str(ent.get("name") or pascal(ekey)) + "管理",
            "title": str(ent.get("title") or ent.get("name") or pascal(ekey)),
            "subtitle": str(ent.get("subtitle") or ""),
            "route": f"{key}/{ekey}",          # 前端相对路由（无前导斜杠）
            "menu_path": f"/{key}/{ekey}",     # 菜单绝对路径
            "class": pascal(ekey),
            "table": f"{key}_{ekey}",
            "fields": fields,
            "sort": int(ent.get("sort") or (out["sort"] + i + 1)),
        })
    return out


def load_spec(raw: Any) -> dict:
    """raw 可以是 dict，也可以是 YAML 文本；返回规范化后的 spec。"""
    if isinstance(raw, (str, bytes)):
        raw = yaml.safe_load(raw) or {}
    return norm_spec(raw)


# ---------------------------------------------------------------------------
# 代码片段生成（后端）
# ---------------------------------------------------------------------------

def sa_type_expr(f: dict) -> str:
    t = f["type"]
    if t == "string":
        return "String(%d)" % f["len"]
    if t == "enum":
        maxlen = max([len(c) for c in f["choices"]] + [16]) + 8
        return "String(%d)" % maxlen
    if t == "text":
        return "Text"
    if t == "int" or t == "fk":
        return "Integer"
    if t == "decimal":
        return "Numeric(%d, %d)" % (f["precision"], f["scale"])
    if t == "bool":
        return "Boolean"
    if t == "date":
        return "Date"
    if t == "datetime":
        return "DateTime(timezone=True)"
    if t == "json":
        return "JSONB"
    return "String(255)"


def py_annot(f: dict) -> str:
    base = PY_TYPES[f["type"]]
    if f["required"]:
        return base
    return f"{base} | None"


def models_column(f: dict) -> str:
    parts = [sa_type_expr(f)]
    if f["required"]:
        parts.append("nullable=False")
    else:
        parts.append("nullable=True")
    if "default" in f and f["default"] is not None:
        d = f["default"]
        if f["type"] == "bool":
            parts.append("default=%s" % ("True" if d else "False"))
        elif f["type"] in ("int", "fk"):
            parts.append("default=%d" % int(d))
        elif f["type"] == "decimal":
            parts.append(f"default={float(d)!r}")
        else:
            parts.append(f"default={str(d)!r}")
    if f["unique"]:
        parts.append("unique=True")
    if f["index"] or f["type"] == "fk":
        parts.append("index=True")
    return "    {}: Mapped[{}] = mapped_column({})".format(snake(f["name"]), py_annot(f), ", ".join(parts))


def render_models(spec: dict, rel: bool = True) -> str:
    used = {f["type"] for e in spec["entities"] for f in e["fields"]}
    need_jsonb = "json" in used
    need_date = "date" in used
    import_line = "from datetime import date, datetime" if need_date else "from datetime import datetime"
    sa_names = ["Integer", "DateTime"]
    if "bool" in used:
        sa_names.append("Boolean")
    if "date" in used:
        sa_names.append("Date")
    if "decimal" in used:
        sa_names.append("Numeric")
    if used & {"string", "enum"}:
        sa_names.append("String")
    if "text" in used:
        sa_names.append("Text")
    sa_names.append("func")
    sa_names = sorted(set(sa_names))
    lines = [
        '"""{} — ORM 模型（由代码生成器生成，可按需手改）"""'.format(spec["name"]),
        import_line,
        "from sqlalchemy import {}".format(", ".join(sa_names)),
    ]
    if need_jsonb:
        lines.append("from sqlalchemy.dialects.postgresql import JSONB")
    lines += [
        "from sqlalchemy.orm import Mapped, mapped_column",
        "",
        "from cenkor_admin.core.db import Base",
        "",
        "",
    ]
    for e in spec["entities"]:
        lines.append("class {}(Base):".format(e["class"]))
        lines.append('    __tablename__ = "{}"'.format(e["table"]))
        lines.append("")
        lines.append("    id: Mapped[int] = mapped_column(Integer, primary_key=True)")
        for f in e["fields"]:
            lines.append(models_column(f))
        lines.append("    creator_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)")
        lines.append("    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)")
        lines.append("    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())")
        lines.append("    updated_at: Mapped[datetime] = mapped_column(")
        lines.append("        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()")
        lines.append("    )")
        lines.append("")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _dict_value_expr(f: dict, var: str) -> str:
    """_to_dict 中某字段的序列化表达式"""
    col = "{}.{}".format(var, snake(f["name"]))
    t = f["type"]
    if t in ("datetime", "date"):
        return f'{col}.isoformat() if {col} else None'
    if t == "decimal":
        return f'float({col}) if {col} is not None else None'
    return col


def render_router(spec: dict) -> str:
    key = spec["key"]
    # 是否需要 or_ / Response
    need_or = any(any(f["search"] for f in e["fields"]) for e in spec["entities"])
    sa_imports = ["func", "select"]
    if need_or:
        sa_imports.append("or_")

    out = [
        '"""{} — CRUD 路由（由代码生成器生成）'.format(spec["name"]),
        "",
        "约定：",
        '  · 每个端点用 require_permission("<key>:<entity>:<action>") 守卫',
        "  · 列表支持 search 模糊搜索 + 指定字段精确过滤 + 分页",
        "  · 删除为软删（写 deleted_at）",
        '  · 生成器不覆盖的地方标了 # TODO(business)，可自行补充业务校验/跨 App 写',
        '"""',
        "from datetime import datetime, timezone",
        "",
        "from fastapi import APIRouter, Depends, HTTPException, Query",
        "from fastapi.responses import Response",
        "from sqlalchemy import {}".format(", ".join(sorted(sa_imports))),
        "from sqlalchemy.ext.asyncio import AsyncSession",
        "",
        "from cenkor_admin.api.deps import require_permission",
        "from cenkor_admin.apps.auth import models as auth_models",
        "from cenkor_admin.core.db import get_db",
        "from . import models",
        "",
        "router = APIRouter()",
        "",
        "",
    ]

    for e in spec["entities"]:
        cls = e["class"]
        ekey = e["key"]
        fields = e["fields"]
        cols = [snake(f["name"]) for f in fields]
        searchable = [snake(f["name"]) for f in fields if f["search"]]
        filterable = [f for f in fields if f["filter"]]
        [snake(f["name"]) for f in fields if f["required"] and f["type"] != "bool"]

        # _to_dict
        out.append(f"def _to_dict_{ekey}(obj: models.{cls}) -> dict:")
        out.append("    return {")
        out.append('        "id": obj.id,')
        for f in fields:
            out.append('        "{}": {},'.format(snake(f["name"]), _dict_value_expr(f, "obj")))
        out += [
            '        "creator_id": obj.creator_id,',
            '        "created_at": obj.created_at.isoformat() if obj.created_at else None,',
            '        "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,',
            "    }",
            "",
            "",
        ]

        # list
        out.append(f'@router.get("/{ekey}")')
        out.append(f"async def list_{ekey}(")
        out.append("    db: AsyncSession = Depends(get_db),")
        out.append(f'    _: auth_models.User = Depends(require_permission("{key}:{ekey}:read")),')
        out.append("    search: str | None = None,")
        for f in filterable:
            out.append("    {}: {} = None,".format(snake(f["name"]), _filter_param_type(f)))
        out.append("    page: int = Query(1, ge=1),")
        out.append("    page_size: int = Query(20, ge=1, le=200),")
        out.append("):")
        out.append(f"    stmt = select(models.{cls}).where(models.{cls}.deleted_at.is_(None))")
        if searchable:
            out.append("    if search:")
            out.append('        like = f"%{search}%"')
            conds = " | ".join(f"models.{cls}.{c}.ilike(like)" for c in searchable)
            if len(searchable) > 1:
                out.append(f"        stmt = stmt.where({conds})")
            else:
                out.append(f"        stmt = stmt.where({conds})")
        for f in filterable:
            c = snake(f["name"])
            out.append(f"    if {c} is not None:")
            if f["type"] == "string" or f["type"] == "enum":
                out.append(f'        stmt = stmt.where(models.{cls}.{c} == {c})')
            else:
                out.append(f'        stmt = stmt.where(models.{cls}.{c} == {c})')
        out.append("    total = (await db.execute(")
        out.append("        select(func.count()).select_from(stmt.subquery())")
        out.append("    )).scalar() or 0")
        out.append(f"    stmt = stmt.order_by(models.{cls}.updated_at.desc())")
        out.append("    stmt = stmt.offset((page - 1) * page_size).limit(page_size)")
        out.append("    items = (await db.execute(stmt)).scalars().all()")
        out.append("    return {")
        out.append(f'        "items": [_to_dict_{ekey}(o) for o in items],')
        out.append('        "total": total,')
        out.append('        "page": page,')
        out.append('        "page_size": page_size,')
        out.append("    }")
        out.append("")
        out.append("")

        # export (declared BEFORE /{item_id})
        out.append(f'@router.get("/{ekey}/export")')
        out.append(f"async def export_{ekey}(")
        out.append("    db: AsyncSession = Depends(get_db),")
        out.append(f'    _: auth_models.User = Depends(require_permission("{key}:{ekey}:export")),')
        out.append("):")
        out.append(f"    stmt = select(models.{cls}).where(models.{cls}.deleted_at.is_(None))")
        out.append(f"    stmt = stmt.order_by(models.{cls}.updated_at.desc())")
        out.append("    items = (await db.execute(stmt)).scalars().all()")
        out.append(f'    header = ["id"] + {cols!r} + ["creator_id", "created_at", "updated_at"]')
        out.append('    lines = [",".join(header)]')
        out.append("    for o in items:")
        out.append(f"        d = _to_dict_{ekey}(o)")
        out.append('        lines.append(",".join(str(d.get(k, "")) for k in header))')
        out.append('    csv = "\\ufeff" + "\\n".join(lines)')
        out.append('    return Response(csv, media_type="text/csv", headers={')
        out.append(f'        "Content-Disposition": \'attachment; filename="{ekey}.csv"\'}}')
        out.append("    )")
        out.append("")
        out.append("")

        # create
        out.append(f'@router.post("/{ekey}", status_code=201)')
        out.append(f"async def create_{ekey}(")
        out.append("    body: dict,")
        out.append("    db: AsyncSession = Depends(get_db),")
        out.append(f'    current: auth_models.User = Depends(require_permission("{key}:{ekey}:write")),')
        out.append("):")
        out.append("    # TODO(business): 在此补充跨 App 写 / 业务校验")
        out.append(f"    obj = models.{cls}()")
        for f in fields:
            c = snake(f["name"])
            out.append(f'    if "{c}" in body:')
            out.append(f'        obj.{c} = body["{c}"]')
        for f in fields:
            if f["required"] and f["type"] != "bool":
                c = snake(f["name"])
                out.append(f'    if obj.{c} in (None, ""):')
                out.append(f'        raise HTTPException(400, "{c} is required")')
        out.append("    obj.creator_id = current.id")
        out.append("    db.add(obj)")
        out.append("    await db.commit()")
        out.append("    await db.refresh(obj)")
        out.append(f"    return _to_dict_{ekey}(obj)")
        out.append("")
        out.append("")

        # detail
        out.append(f'@router.get("/{ekey}/{{item_id}}")')
        out.append(f"async def get_{ekey}(")
        out.append("    item_id: int,")
        out.append("    db: AsyncSession = Depends(get_db),")
        out.append(f'    _: auth_models.User = Depends(require_permission("{key}:{ekey}:read")),')
        out.append("):")
        out.append(f"    obj = await db.get(models.{cls}, item_id)")
        out.append("    if not obj or obj.deleted_at:")
        out.append('        raise HTTPException(404, "not found")')
        out.append(f"    return _to_dict_{ekey}(obj)")
        out.append("")
        out.append("")

        # update
        out.append(f'@router.patch("/{ekey}/{{item_id}}")')
        out.append(f"async def update_{ekey}(")
        out.append("    item_id: int,")
        out.append("    body: dict,")
        out.append("    db: AsyncSession = Depends(get_db),")
        out.append(f'    _: auth_models.User = Depends(require_permission("{key}:{ekey}:write")),')
        out.append("):")
        out.append(f"    obj = await db.get(models.{cls}, item_id)")
        out.append("    if not obj or obj.deleted_at:")
        out.append('        raise HTTPException(404, "not found")')
        out.append("    # TODO(business): 在此补充业务校验")
        cols_tuple = ", ".join(f'"{c}"' for c in cols)
        out.append(f"    for field in ({cols_tuple}):")
        out.append("        if field in body:")
        out.append("            setattr(obj, field, body[field])")
        out.append("    await db.commit()")
        out.append("    await db.refresh(obj)")
        out.append(f"    return _to_dict_{ekey}(obj)")
        out.append("")
        out.append("")

        # delete (soft)
        out.append(f'@router.delete("/{ekey}/{{item_id}}", status_code=204)')
        out.append(f"async def delete_{ekey}(")
        out.append("    item_id: int,")
        out.append("    db: AsyncSession = Depends(get_db),")
        out.append(f'    _: auth_models.User = Depends(require_permission("{key}:{ekey}:delete")),')
        out.append("):")
        out.append(f"    obj = await db.get(models.{cls}, item_id)")
        out.append("    if not obj or obj.deleted_at:")
        out.append('        raise HTTPException(404, "not found")')
        out.append("    obj.deleted_at = datetime.now(timezone.utc)")
        out.append("    await db.commit()")
        out.append("")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _filter_param_type(f: dict) -> str:
    t = f["type"]
    if t in ("int", "fk"):
        return "int | None"
    if t == "bool":
        return "bool | None"
    if t == "decimal":
        return "float | None"
    if t == "date":
        return "str | None"
    if t == "datetime":
        return "str | None"
    return "str | None"


# ---------------------------------------------------------------------------
# 代码片段生成（迁移）
# ---------------------------------------------------------------------------

def mig_column(f: dict) -> str:
    name = snake(f["name"])
    t = f["type"]
    if t == "string":
        expr = "sa.String(length=%d)" % f["len"]
    elif t == "enum":
        maxlen = max([len(c) for c in f["choices"]] + [16]) + 8
        expr = "sa.String(length=%d)" % maxlen
    elif t == "text":
        expr = "sa.Text()"
    elif t in ("int", "fk"):
        expr = "sa.Integer()"
    elif t == "decimal":
        expr = "sa.Numeric(precision=%d, scale=%d)" % (f["precision"], f["scale"])
    elif t == "bool":
        expr = "sa.Boolean()"
    elif t == "date":
        expr = "sa.Date()"
    elif t == "datetime":
        expr = "sa.DateTime(timezone=True)"
    elif t == "json":
        expr = "postgresql.JSONB()"
    else:
        expr = "sa.String(length=255)"
    nullable = "False" if f["required"] else "True"
    sd = ""
    if f.get("default") is not None:
        d = f["default"]
        if t == "bool":
            sd = ", server_default=sa.text('%s')" % ("true" if d else "false")
        elif t in ("int", "fk"):
            sd = ", server_default=sa.text('%d')" % int(d)
        elif t == "decimal":
            sd = f", server_default=sa.text('{d!s}')"
        elif t in ("string", "enum", "text"):
            sd = f", server_default={str(d)!r}"
    return f'        sa.Column("{name}", {expr}, nullable={nullable}{sd}),'


def render_migration(spec: dict, head: str) -> tuple:
    key = spec["key"]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    rev = (f"{ts}_gen_{key}")[:32]
    fname = f"{ts}_create_{key}.py"
    lines = [
        f'"""create {key} tables',
        "",
        f"Revision ID: {rev}",
        f"Revises: {head}",
        "Create Date: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")),
        "",
        '"""',
        "from alembic import op",
        "import sqlalchemy as sa",
    ]
    if any(f["type"] == "json" for e in spec["entities"] for f in e["fields"]):
        lines.append("from sqlalchemy.dialects import postgresql")
    lines += [
        "",
        f'revision = "{rev}"',
        f'down_revision = "{head}"',
        "branch_labels = None",
        "depends_on = None",
        "",
        "",
        "def upgrade() -> None:",
    ]
    for e in spec["entities"]:
        lines.append('    op.create_table(')
        lines.append('        "{}",'.format(e["table"]))
        lines.append('        sa.Column("id", sa.Integer(), primary_key=True),')
        for f in e["fields"]:
            lines.append(mig_column(f))
        lines.append('        sa.Column("creator_id", sa.Integer(), nullable=False),')
        lines.append('        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),')
        lines.append('        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),')
        lines.append('        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),')
        lines.append('    )')
        lines.append('    op.create_index("ix_{}_creator_id", "{}", ["creator_id"])'.format(e["table"], e["table"]))
        for f in e["fields"]:
            c = snake(f["name"])
            if f["unique"]:
                lines.append('    op.create_index("uq_{}_{}", "{}", ["{}"], unique=True)'.format(e["table"], c, e["table"], c))
            elif f["index"] or f["type"] == "fk":
                lines.append('    op.create_index("ix_{}_{}", "{}", ["{}"])'.format(e["table"], c, e["table"], c))
        lines.append("")
    lines += [
        "",
        "def downgrade() -> None:",
    ]
    for e in reversed(spec["entities"]):
        for f in e["fields"]:
            c = snake(f["name"])
            if f["unique"]:
                lines.append('    op.drop_index("uq_{}_{}", table_name="{}")'.format(e["table"], c, e["table"]))
            elif f["index"] or f["type"] == "fk":
                lines.append('    op.drop_index("ix_{}_{}", table_name="{}")'.format(e["table"], c, e["table"]))
        lines.append('    op.drop_index("ix_{}_creator_id", table_name="{}")'.format(e["table"], e["table"]))
        lines.append('    op.drop_table("{}")'.format(e["table"]))
    return fname, rev, "\n".join(lines) + "\n"


_DOWN_RE = re.compile(
    r"(down_revision(?:\s*:\s*[^=\n]+)?\s*=\s*)(?:['\"][^'\"]*['\"]|None)"
)


def _rewrite_down_revision(path: Path, new_head: str) -> bool:
    """把迁移文件里的 down_revision 改写为 new_head（只动这一行）。返回是否有改动。"""
    content = path.read_text(encoding="utf-8")
    new_content = _DOWN_RE.sub(lambda m: m.group(1) + repr(new_head), content, count=1)
    if new_content == content:
        return False
    path.write_text(new_content, encoding="utf-8")
    return True


def rebase_closed_chain(versions_dir: Path, old_head: str, new_rev: str,
                        exclude: set[str] | None = None) -> list[tuple[str, str]]:
    """内置模式：把「挂在开源链旧 head 下的闭源迁移」顺延挂到新迁移之下。

    为什么必须做：闭源商业应用（erp/crm/mes/commerce…）的迁移入口挂在最靠后的开源
    迁移上。新增一条开源迁移后，若不把该入口顺延，它仍指向旧 head —— 全量视图就会出现
    两个 head（新迁移 + 闭源链尾），alembic 直接拒绝 upgrade；而反过来把新开源迁移挂到
    闭源迁移之下又违反「开源迁移绝不挂在闭源之下」的铁律。故：只把 down_revision 恰好
    等于旧 head 的「非 git 跟踪」迁移重挂到新迁移。

    返回 [(文件名, 新 down_revision), ...]。
    """
    tracked = git_tracked_names(versions_dir)
    if tracked is None:
        raise SystemExit("✗ 内置模式需要 git 来识别闭源迁移，但未找到 git 命令")
    exclude = exclude or set()
    rebased = []
    for f in all_migration_files(versions_dir):
        if f.name.startswith("__") or f.name in tracked or f.name in exclude:
            continue
        _rev, down = parse_migration(f)
        if down == old_head and _rewrite_down_revision(f, new_rev):
            rebased.append((f.name, new_rev))
    return rebased


# ---------------------------------------------------------------------------
# 代码片段生成（manifest / __init__）
# ---------------------------------------------------------------------------

def render_permissions(spec: dict) -> list:
    key = spec["key"]
    perms = []
    for e in spec["entities"]:
        for act in ("read", "write", "delete", "export"):
            perms.append("{}:{}:{}".format(key, e["key"], act))
    perms.append(f"{key}:admin")
    return perms


def render_manifest(spec: dict) -> str:
    key = spec["key"]
    perms = render_permissions(spec)
    lines = [
        '"""{} — AppManifest（由代码生成器生成）"""'.format(spec["name"]),
        "from __future__ import annotations",
        "",
        "from cenkor_admin.apps.base import AppManifest",
        "",
        "",
        "MANIFEST = AppManifest(",
        f'    key="{key}",',
        '    name="{}",'.format(spec["name"]),
        '    version="{}",'.format(spec["version"]),
        '    author={!r},'.format(spec["author"]),
        '    description=%r,' % (spec["description"] or "{}（CRUD 应用）".format(spec["name"])),
        '    icon="{}",'.format(spec["icon"]),
        '    category="{}",'.format(spec["category"]),
        "    permissions_required=[",
    ]
    for p in perms:
        lines.append(f'        "{p}",')
    lines += [
        "    ],",
        "    menus=[",
        "        {",
        f'            "key": "{key}",',
        '            "title": "{}",'.format(spec["name"]),
        '            "icon": "%s",' % (spec.get("menu_icon") or "appstore"),
        '            "sort": %d,' % spec["sort"],
        '            "children": [',
    ]
    for e in spec["entities"]:
        lines += [
            "                {",
            '                    "key": "{}:{}",'.format(key, e["key"]),
            '                    "title": "{}",'.format(e["title"]),
            '                    "path": "{}",'.format(e["menu_path"]),
            '                    "icon": "menu",',
            '                    "sort": %d,' % e["sort"],
            "                },",
        ]
    lines += [
        "            ],",
        "        },",
        "    ],",
        f'    public_routes_prefix="/api/v1/{key}",',
        ")",
        "",
    ]
    return "\n".join(lines)


def render_init(spec: dict) -> str:
    return '"""{}"""\nfrom .manifest import MANIFEST\n\n__all__ = ["MANIFEST"]\n'.format(spec["name"])


# ---------------------------------------------------------------------------
# 代码片段生成（前端源码 —— 供二次开发时 npm build 覆写 dist）
# ---------------------------------------------------------------------------

def vue_control(f: dict) -> str:
    c = snake(f["name"])
    t = f["type"]
    label = f["label"]
    if t == "text":
        return (f'        <el-form-item label="{label}" prop="{c}">\n'
                f'          <el-input v-model="form.{c}" type="textarea" :rows="3" />\n'
                '        </el-form-item>')
    if t == "int":
        return (f'        <el-form-item label="{label}" prop="{c}">\n'
                f'          <el-input-number v-model="form.{c}" :min="0" style="width: 200px" />\n'
                '        </el-form-item>')
    if t == "fk":
        return ('        <!-- TODO(business): fk 远程下拉为 P1，先用数字输入 -->\n'
                f'        <el-form-item label="{label}" prop="{c}">\n'
                f'          <el-input-number v-model="form.{c}" :min="0" style="width: 200px" />\n'
                '        </el-form-item>')
    if t == "decimal":
        return ('        <el-form-item label="%s" prop="%s">\n'
                '          <el-input-number v-model="form.%s" :precision="%d" :step="0.01" style="width: 200px" />\n'
                '        </el-form-item>' % (label, c, c, f["scale"]))
    if t == "bool":
        return (f'        <el-form-item label="{label}" prop="{c}">\n'
                f'          <el-switch v-model="form.{c}" />\n'
                '        </el-form-item>')
    if t == "date":
        return (f'        <el-form-item label="{label}" prop="{c}">\n'
                f'          <el-date-picker v-model="form.{c}" type="date" value-format="YYYY-MM-DD" style="width: 200px" />\n'
                '        </el-form-item>')
    if t == "datetime":
        return (f'        <el-form-item label="{label}" prop="{c}">\n'
                f'          <el-date-picker v-model="form.{c}" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" style="width: 220px" />\n'
                '        </el-form-item>')
    if t == "enum":
        opts = "".join(
            f'\n            <el-option label="{ch}" value="{ch}" />' for ch in f["choices"]
        )
        return (f'        <el-form-item label="{label}" prop="{c}">\n'
                f'          <el-select v-model="form.{c}" placeholder="请选择" clearable style="width: 200px">{opts}\n'
                '          </el-select>\n'
                '        </el-form-item>')
    if t == "json":
        return ('        <!-- json 字段：高级表单暂不生成，需要时手写 -->\n'
                f'        <el-form-item label="{label}" prop="{c}">\n'
                f'          <el-input v-model="form._{c}_raw" type="textarea" :rows="3" placeholder=\'JSON，如 {{"k": "v"}}\' />\n'
                '        </el-form-item>')
    # string 默认
    return (f'        <el-form-item label="{label}" prop="{c}">\n'
            f'          <el-input v-model="form.{c}" />\n'
            '        </el-form-item>')


def vue_column(f: dict) -> str:
    c = snake(f["name"])
    label = f["label"]
    t = f["type"]
    width = f.get("width") or (140 if t in ("datetime",) else 120)
    if t == "bool":
        return (f'  {{ prop: "{c}", label: "{label}", width: 90, formatter: (r) => (r.{c} ? "是" : "否") }},')
    if t == "enum":
        mapping = "{" + ", ".join(f"'{ch}': '{ch}'" for ch in f["choices"]) + "}"
        return (f'  {{ prop: "{c}", label: "{label}", width: 110, formatter: (r) => ({mapping}[r.{c}] || r.{c} || "—") }},')
    if t == "decimal":
        return (f'  {{ prop: "{c}", label: "{label}", width: 120, formatter: (r) => fmtMoney(r.{c}) }},')
    if t in ("date", "datetime"):
        return (f'  {{ prop: "{c}", label: "{label}", width: 120, formatter: (r) => fmtDate(r.{c}) }},')
    if t == "text":
        return (f'  {{ prop: "{c}", label: "{label}", minWidth: 160, formatter: (r) => {{ const v = r.{c}; return v && v.length > 30 ? v.slice(0, 30) + "…" : (v || "—") }} }},')
    return '  { prop: "%s", label: "%s", width: %d },' % (c, label, width)


def vue_search_field(f: dict) -> str:
    c = snake(f["name"])
    label = f["label"]
    t = f["type"]
    if t == "enum":
        opts = ", ".join(f"{{ value: '{ch}', label: '{ch}' }}" for ch in f["choices"])
        return f"  {{ prop: '{c}', label: '{label}', type: 'select', options: [{opts}] }},"
    if t == "bool":
        return f"  {{ prop: '{c}', label: '{label}', type: 'select', options: [{{ value: true, label: '是' }}, {{ value: false, label: '否' }}] }},"
    return f"  {{ prop: '{c}', label: '{label}', type: 'input', placeholder: '请输入{label}' }},"


def vue_rules(f: dict) -> str:
    c = snake(f["name"])
    label = f["label"]
    t = f["type"]
    if not f["required"] or t == "bool":
        return ""
    trigger = "change" if t in ("enum", "date", "datetime", "int", "decimal", "fk") else "blur"
    return f"  {c}: [{{ required: true, message: '{label}必填', trigger: '{trigger}' }}],\n"


def render_page(spec: dict, e: dict) -> str:
    ekey = e["key"]
    e["class"]
    spec["name"]
    fields = e["fields"]
    list_cols = [f for f in fields if f["list"]]
    search_fields = [f for f in fields if f["search"]]
    form_fields = fields

    # template
    t = ['<template>']
    t.append('  <PageShell title="{}"{}>'.format(e["title"], (' subtitle="{}"'.format(e["subtitle"])) if e["subtitle"] else ""))
    t.append('    <template #actions>')
    t.append('      <el-button type="primary" :icon="Plus" @click="openCreate">新建</el-button>')
    t.append('    </template>')
    t.append('')
    if search_fields:
        t.append('    <SearchBar :fields="searchFields" @search="onSearch" />')
        t.append('')
    t.append('    <DataTable :data="rows" :columns="columns" :total="total" :page="page" :page-size="pageSize"')
    t.append('               :loading="loading" @update:page="load" @update:pageSize="onSizeChange">')
    t.append('      <template #operation>')
    t.append('        <el-table-column label="操作" width="140" align="center" fixed="right">')
    t.append('          <template #default="{ row }">')
    t.append('            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>')
    t.append('            <el-button link type="danger" @click="onDelete(row)">删除</el-button>')
    t.append('          </template>')
    t.append('        </el-table-column>')
    t.append('      </template>')
    t.append('    </DataTable>')
    t.append('')
    t.append('    <FormDrawer v-model="drawerVisible" :title="drawerTitle" :saving="saving" @save="onSave">')
    t.append('      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">')
    for f in form_fields:
        t.append(vue_control(f))
    t.append('      </el-form>')
    t.append('    </FormDrawer>')
    t.append('  </PageShell>')
    t.append('</template>')
    t.append('')

    # script
    t.append('<script setup>')
    t.append("import { ref, reactive, onMounted } from 'vue'")
    t.append("import { ElMessage, ElMessageBox } from 'element-plus'")
    t.append("import { Plus } from '@element-plus/icons-vue'")
    t.append("import PageShell from '../components/PageShell.vue'")
    t.append("import SearchBar from '../components/SearchBar.vue'")
    t.append("import DataTable from '../components/DataTable.vue'")
    t.append("import FormDrawer from '../components/FormDrawer.vue'")
    t.append("import { api, fmtMoney, fmtDate } from '../api'")
    t.append('')
    t.append(f"const RES = '/{ekey}'")
    t.append('const rows = ref([])')
    t.append('const total = ref(0)')
    t.append('const page = ref(1)')
    t.append('const pageSize = ref(20)')
    t.append('const loading = ref(false)')
    t.append('const saving = ref(false)')
    t.append('const drawerVisible = ref(false)')
    t.append('const drawerTitle = ref("新建")')
    t.append('const formRef = ref(null)')
    t.append("const editingId = ref(null)")
    t.append('')
    t.append('const filters = reactive({})')
    t.append('')
    # search fields
    if search_fields:
        t.append('const searchFields = [')
        for f in search_fields:
            t.append(vue_search_field(f))
        t.append(']')
    else:
        t.append('const searchFields = []')
    t.append('')
    # columns
    t.append('const columns = [')
    for f in list_cols:
        t.append(vue_column(f))
    t.append(']')
    t.append('')
    # form defaults
    defaults = []
    for f in form_fields:
        c = snake(f["name"])
        if f.get("default") is not None:
            d = f["default"]
            if f["type"] == "bool":
                defaults.append("{}: {}".format(c, "true" if d else "false"))
            elif f["type"] in ("int", "fk", "decimal"):
                defaults.append(f"{c}: {d}")
            else:
                defaults.append("{}: {}".format(c, repr(str(d)).replace("'", "'")))
        elif f["type"] == "bool":
            defaults.append(f"{c}: false")
        else:
            defaults.append(f"{c}: null")
    t.append('function emptyForm() {')
    t.append('  return {{ {} }}'.format(", ".join(defaults)))
    t.append('}')
    t.append('const form = reactive(emptyForm())')
    t.append('')
    # rules
    rules_body = "".join(vue_rules(f) for f in form_fields)
    t.append('const rules = {')
    if rules_body:
        t.append(rules_body.rstrip("\n"))
    t.append('}')
    t.append('')
    # load
    t.append('async function load(p = 1) {')
    t.append('  page.value = p')
    t.append('  loading.value = true')
    t.append('  try {')
    t.append('    const params = { page: page.value, page_size: pageSize.value }')
    t.append('    for (const [k, v] of Object.entries(filters)) {')
    t.append("      if (v !== '' && v !== null && v !== undefined) params[k] = v")
    t.append('    }')
    t.append('    const data = await api.get(RES, params)')
    t.append('    rows.value = data.items || []')
    t.append('    total.value = data.total || 0')
    t.append("  } catch (e) { ElMessage.error(e.message) } finally { loading.value = false }")
    t.append('}')
    t.append('')
    t.append('function onSearch(q) {')
    t.append('  Object.keys(filters).forEach((k) => delete filters[k])')
    t.append('  Object.assign(filters, q || {})')
    t.append('  load(1)')
    t.append('}')
    t.append('function onSizeChange(s) { pageSize.value = s; load(1) }')
    t.append('')
    t.append('function openCreate() {')
    t.append("  editingId.value = null")
    t.append('  Object.assign(form, emptyForm())')
    t.append('  drawerTitle.value = "新建"')
    t.append('  drawerVisible.value = true')
    t.append('}')
    t.append('function openEdit(row) {')
    t.append('  editingId.value = row.id')
    t.append('  Object.assign(form, emptyForm())')
    t.append('  Object.assign(form, row)')
    t.append('  drawerTitle.value = "编辑"')
    t.append('  drawerVisible.value = true')
    t.append('}')
    t.append('')
    t.append('async function onSave() {')
    t.append('  if (formRef.value) {')
    t.append('    const ok = await formRef.value.validate().catch(() => false)')
    t.append('    if (!ok) return')
    t.append('  }')
    t.append('  saving.value = true')
    t.append('  try {')
    t.append('    if (editingId.value) {')
    t.append('      await api.patch(RES + "/" + editingId.value, form)')
    t.append("      ElMessage.success('已更新')")
    t.append('    } else {')
    t.append('      await api.post(RES, form)')
    t.append("      ElMessage.success('已创建')")
    t.append('    }')
    t.append('    drawerVisible.value = false')
    t.append('    load(editingId.value ? page.value : 1)')
    t.append("  } catch (e) { ElMessage.error(e.message) } finally { saving.value = false }")
    t.append('}')
    t.append('')
    t.append('function onDelete(row) {')
    t.append("  ElMessageBox.confirm('确认删除该记录？', '提示', { type: 'warning' })")
    t.append('    .then(async () => {')
    t.append('      try {')
    t.append('        await api.del(RES + "/" + row.id)')
    t.append("        ElMessage.success('已删除')")
    t.append('        load(page.value)')
    t.append("      } catch (e) { ElMessage.error(e.message) }")
    t.append('    })')
    t.append('    .catch(() => {})')
    t.append('}')
    t.append('')
    t.append('onMounted(() => load(1))')
    t.append('</script>')
    t.append('')
    t.append('<style scoped></style>')
    t.append('')
    return "\n".join(t)


def render_main_js(spec: dict) -> str:
    key = spec["key"]
    routes = []
    menus = []
    imports = []
    for e in spec["entities"]:
        comp = "{}View".format(e["class"])
        imports.append("import {} from './pages/{}View.vue'".format(comp, e["class"]))
        routes.append(
            '    {{ path: \'{}\', name: \'{}-{}\', component: {}, meta: {{ permission: \'{}:{}:read\' }} }},'.format(e["route"], key, e["key"], comp, key, e["key"])
        )
        menus.append(
            '    { key: \'%s:%s\', title: \'%s\', path: \'%s\', icon: \'menu\', sort: %d },'
            % (key, e["key"], e["title"], e["menu_path"], e["sort"])
        )
    lines = [
        "// {} 前端插件入口 —— 打包为 iife 单文件 plugin.js（由代码生成器生成）".format(spec["name"]),
        "import 'vue'",
        "import ElementPlusCss from 'element-plus/dist/index.css?inline'",
        "",
    ]
    lines += imports
    lines += [
        "",
        "if (typeof document !== 'undefined') {",
        "  const style = document.createElement('style')",
        f"  style.setAttribute('data-{key}-plugin', 'element-plus')",
        "  style.textContent = ElementPlusCss",
        "  document.head.appendChild(style)",
        "}",
        "",
        "// 路由 path 必须与后端 manifest menus 的 path 一致（此处相对路径无前导斜杠）",
        "window.__registerPlugin({",
        f"  id: '{key}',",
        "  version: '{}',".format(spec["version"]),
        "  name: '{}',".format(spec["name"]),
        "  routes: [",
    ]
    lines += routes
    lines += [
        "  ],",
        "  menus: [",
    ]
    lines += menus
    lines += [
        "  ],",
        "  locales: {",
        "    'zh-CN': {{ {}: {{ title: '{}' }} }}".format(key, spec["name"]),
        "  }",
        "})",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 运行时插件（零构建资产）：plugin.js = 内嵌 spec 的前言 + 预构建的通用 CRUD 运行时
# ---------------------------------------------------------------------------

def plugin_head_source() -> str:
    p = ASSETS_DIR / PLUGIN_HEAD_NAME
    if not p.exists():
        raise SystemExit(
            f"✗ 缺少前端运行时插件资产：{p}\n"
            "  生成 App 需要它（每个 App 复用同一份通用 CRUD 运行时）。"
            "构建方式见 cenkor_admin/codegen/runtime_plugin/README。"
        )
    return p.read_text(encoding="utf-8")


def app_meta(spec: dict) -> dict:
    """嵌入 plugin.js 的应用元数据（单目标语言：与后端 spec 保持一致）。"""
    return {
        "key": spec["key"],
        "name": spec["name"],
        "version": spec["version"],
        "entities": [
            {
                "key": e["key"],
                "name": e["name"],
                "title": e["title"],
                "subtitle": e["subtitle"],
                "route": e["route"],
                "menu_path": e["menu_path"],
                "sort": e["sort"],
                "fields": e["fields"],
            }
            for e in spec["entities"]
        ],
    }


def render_plugin_js(spec: dict, bundle: str | None = None) -> str:
    """生成 App 的 frontend/dist/plugin.js：前言（元数据）+ 通用运行时 bundle。"""
    if bundle is None:
        bundle = plugin_head_source()
    head = "window.__CODEGEN_APP__ = {};\n".format(json.dumps(
        app_meta(spec), ensure_ascii=False, separators=(",", ":")
    ))
    return head + bundle


# ---------------------------------------------------------------------------
# 静态模板（前端的通用文件，几乎无需按 App 定制）
# ---------------------------------------------------------------------------

FRONTEND_STATIC = [
    "package.json",
    "vite.config.js",
    "src/api.js",
    "src/nav.js",
    "src/components/DataTable.vue",
    "src/components/FormDrawer.vue",
    "src/components/PageShell.vue",
    "src/components/SearchBar.vue",
]


def read_static(templates_dir: Path, rel_paths: list, subs: dict) -> dict:
    """读取模板并替换 @@XXX@@ 占位，返回 {相对路径: 文本}（不落盘）。"""
    out = {}
    for rel in rel_paths:
        src = templates_dir / "frontend" / rel
        if not src.exists():
            raise SystemExit(f"✗ 缺少模板文件：{src}")
        text = src.read_text(encoding="utf-8")
        for k, v in subs.items():
            text = text.replace(f"@@{k}@@", v)
        out["frontend/" + rel] = text
    return out


# ---------------------------------------------------------------------------
# 组装
# ---------------------------------------------------------------------------

def resolve_head(versions_dir: Path, mode: str) -> str:
    if mode == "builtin":
        return tracked_head(versions_dir)
    return current_head(versions_dir)


def build_files(raw: dict, mode: str = "package", versions_dir: os.PathLike | str | None = None,
                templates_dir: os.PathLike | str | None = None,
                plugin_bundle: str | None = None,
                include_plugin: bool = True) -> dict:
    """生成 App 的全部文件，返回 {相对 App 根路径: 文本}。**不写磁盘**。

    :param raw:             spec 原始 dict（未规范化）
    :param mode:            package（迁移随包分发）| builtin（迁移写全局链，CLI 用）
    :param versions_dir:    alembic 全局 versions 目录（用于取 head）
    :param templates_dir:   前端模板目录，默认 codegen/templates/app
    :param plugin_bundle:   运行时插件 bundle 文本；None 时从 assets/plugin_head.js 读取
    :param include_plugin:  是否产出 frontend/dist/plugin.js
    :raises SystemExit:     spec 非法 / 缺模板 / 缺插件资产 / 迁移图非唯一 head
    """
    spec = norm_spec(raw)
    if templates_dir is None:
        templates_dir = DEFAULT_TEMPLATES_DIR
    templates_dir = Path(templates_dir)
    if mode not in ("package", "builtin"):
        raise SystemExit(f"✗ 未知模式：{mode!r}（可选 package / builtin）")

    versions_dir_p = Path(versions_dir) if versions_dir is not None else None
    if mode == "builtin":
        if versions_dir_p is None:
            raise SystemExit("✗ builtin 模式必须提供 versions_dir")
        head = tracked_head(versions_dir_p)
    elif versions_dir_p is not None:
        head = current_head(versions_dir_p)
    else:
        raise SystemExit("✗ 需要 versions_dir 以确定迁移挂载点（down_revision）")

    key = spec["key"]
    files: dict = {}

    # 后端
    files["__init__.py"] = render_init(spec)
    files["manifest.py"] = render_manifest(spec)
    files["models.py"] = render_models(spec, rel=True)
    files["router.py"] = render_router(spec)

    # 迁移（两种模式都放进映射；builtin 由 CLI 落盘到全局链，见 write 逻辑）
    mig_name, _mig_rev, mig_src = render_migration(spec, head)
    files["alembic/versions/" + mig_name] = mig_src

    # 前端模板源码（供二次开发 npm build 覆写 dist）
    subs = {
        "APP_KEY": key,
        "APP_NAME": spec["name"],
        "PLUGIN_NAME": pascal(key) + "Plugin",
        "PKG_NAME": f"{key}-frontend",
    }
    files.update(read_static(templates_dir, FRONTEND_STATIC, subs))

    # 前端动态源码
    for e in spec["entities"]:
        files["frontend/src/pages/{}View.vue".format(e["class"])] = render_page(spec, e)
    files["frontend/src/main.js"] = render_main_js(spec)

    # 零构建运行时插件（每个 App 复用同一份；前言带本 App 元数据）
    if include_plugin:
        files["frontend/dist/plugin.js"] = render_plugin_js(spec, plugin_bundle)

    # spec 存档（便于二次开发/重新生成）
    files["app.spec.yaml"] = yaml.safe_dump(raw, allow_unicode=True, sort_keys=False)

    return files


def write_files(files: dict, out_dir: os.PathLike | str) -> None:
    """把 build_files 的产出写到磁盘。"""
    out = Path(out_dir)
    for rel, text in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def zip_bytes(files: dict) -> bytes:
    """文件映射 → ZIP bytes（包根即 App 根，含 manifest.py/__init__.py，可直接安装）。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, text in sorted(files.items()):
            zf.writestr(rel, text)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------

def self_check(spec: dict, files: dict, versions_dir: os.PathLike | str | None = None,
               mode: str = "package") -> list:
    """对生成结果做静态自检：包结构 / 语法 / 菜单与路由一致 / 迁移链唯一 head。"""
    problems = []
    # 1) 包结构硬性要求
    for req in ("manifest.py", "__init__.py", "models.py", "router.py"):
        if req not in files:
            problems.append(f"缺少必需文件：{req}")
    if "frontend/dist/plugin.js" not in files:
        problems.append("缺少 frontend/dist/plugin.js（App 安装后将无前端界面）")
    # 2) 语法编译（直接编译文本，无需落盘）
    for rel, text in sorted(files.items()):
        if not rel.endswith(".py"):
            continue
        try:
            compile(text, rel, "exec")
        except SyntaxError as exc:
            problems.append(f"语法错误 {rel}：{exc}")
    # 3) 菜单 path 与前端路由 path 一致（源码视图）
    try:
        menu_paths = set(re.findall(r'"path":\s*"(/[^"]+)"', files.get("manifest.py", "")))
        route_paths = set(re.findall(r"path:\s*'([^']+)'", files.get("frontend/src/main.js", "")))
        for mp in menu_paths:
            if mp == "/{}".format(spec["key"]):
                continue  # 顶层菜单，无对应路由
            if mp.lstrip("/") not in route_paths:
                problems.append(f"菜单 path {mp} 在前端 routes 中缺失")
    except Exception as exc:
        problems.append(f"菜单/路由一致性检查失败：{exc}")
    # 4) 运行时插件前言里的菜单 path 与 manifest 一致
    plugin_src = files.get("frontend/dist/plugin.js", "")
    if plugin_src:
        try:
            line = plugin_src.split("\n", 1)[0]
            meta = json.loads(line.split("=", 1)[1].rstrip(";").strip())
            plugin_paths = {e["menu_path"] for e in meta["entities"]}
            manifest_paths = {e["menu_path"] for e in spec["entities"]}
            if plugin_paths != manifest_paths:
                problems.append("运行时插件元数据菜单 path 与 spec 不一致")
            if meta["key"] != spec["key"]:
                problems.append("运行时插件元数据 key 与 spec 不一致")
        except Exception as exc:
            problems.append(f"运行时插件元数据解析失败：{exc}")
    # 5) 迁移图仍唯一 head：内置模式额外校验「开源视图」也唯一 head
    if versions_dir is not None:
        checks = [("全量", current_head)]
        if mode == "builtin":
            checks.append(("开源", tracked_head))
        for scope, fn in checks:
            try:
                fn(Path(versions_dir))
            except SystemExit as exc:
                problems.append(f"{scope}视图迁移图检查失败：{exc}")
    return problems
