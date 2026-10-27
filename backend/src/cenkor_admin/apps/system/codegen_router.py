"""CRUD 代码生成器 API（后台「系统 > 代码生成」页）—— /api/v1/system/codegen

端点：
    GET    /meta              生成器元信息（字段类型、插件资产、迁移 head、已安装 App、样例 spec）
    GET    /tables            只读列出库中的表与列（供「从已有表导入」）
    POST   /preview           校验 + 预览（规范化 spec、YAML、文件清单、自检问题）
    POST   /generate          生成并下载源码 ZIP（包根即 App 根，可直接安装 / 上传开发者中心）
    POST   /install           生成并**安装到本系统**（建表 + 注册权限/菜单 + 动态注册路由，无需重启）
    GET    /runs              执行历史列表（生成 / 安装留痕，不含 spec）
    GET    /runs/{id}         执行详情（含当时的 spec 快照与原始报错）
    POST   /runs/{id}/rerun   按历史记录再次执行（generate → 下载 ZIP；install → 重新安装）
    DELETE /runs/{id}         删除一条历史记录

权限：system:codegen:read（查询 / 历史） / system:codegen:write（预览 / 生成 / 安装 / 再次执行 / 删除）。

history：每次「下载源码包 / 安装到本系统」都会往 codegen_runs 写一条（成功与失败都写，失败
保留后端原始报错原文）。留痕是旁路 —— 任何写库异常都不会影响生成 / 安装本身。

生成核心在 cenkor_admin.codegen.builder（纯 stdlib + PyYAML）。注意：本模块顶层的
yaml / builder 都是**惰性导入**（放到函数内），因为本模块会被 system/router.py 在进程
启动时导入 —— 若 PyYAML 缺失，绝不能因此拖垮整个后端启动。
"""
from __future__ import annotations

import contextlib
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.system.models import CodegenRun, InstalledApp
from cenkor_admin.apps.system.store_router import ALEMBIC_VERSIONS_DIR
from cenkor_admin.core.db import get_db

router = APIRouter()

READY = "system:codegen:read"
WRITE = "system:codegen:write"

_KIND = {
    ".py": "python", ".vue": "vue", ".js": "javascript",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".md": "markdown",
}


def _load_builder():
    """惰性导入生成核心（build_files/norm_spec/self_check/zip_bytes…）。"""
    from cenkor_admin.codegen import builder

    return builder


def _read_spec(body: Any) -> Any:
    """从请求体取 spec，兼容三种写法：

        {"yaml": "<spec YAML 文本>"}   —— 后台页面直接编辑 YAML
        {"spec": {...}}                —— 结构化 spec（等价于 YAML 已解析）
        {...}                          —— 直接把 spec 顶层字段放请求体
    """
    import yaml

    if not isinstance(body, dict):
        raise HTTPException(400, "请求体必须是 JSON 对象")
    if body.get("yaml") is not None:
        try:
            return yaml.safe_load(body["yaml"]) or {}
        except yaml.YAMLError as exc:
            raise HTTPException(400, f"YAML 解析失败：{exc}") from exc
    if body.get("spec") is not None:
        return body["spec"]
    return body


def _generate(raw: Any) -> dict:
    """规范化 + 生成文件映射 + 自检。任何一步不通过都抛 400。"""
    B = _load_builder()
    try:
        spec = B.norm_spec(raw)
    except SystemExit as exc:
        raise HTTPException(400, str(exc)) from exc
    try:
        files = B.build_files(raw, mode="package", versions_dir=ALEMBIC_VERSIONS_DIR)
    except SystemExit as exc:
        raise HTTPException(400, str(exc)) from exc
    problems = B.self_check(spec, files, versions_dir=ALEMBIC_VERSIONS_DIR, mode="package")
    if problems:
        raise HTTPException(400, "生成物自检未通过：" + "；".join(problems))
    return {"builder": B, "spec": spec, "files": files}


def _migration_head() -> tuple:
    """当前平台迁移链 head。返回 (head, error)。"""
    B = _load_builder()
    try:
        return B.current_head(ALEMBIC_VERSIONS_DIR), None
    except SystemExit as exc:
        return None, str(exc)


# ---------------------------------------------------------------------------
# 执行历史（codegen_runs）
# ---------------------------------------------------------------------------

def _peek_key(raw: Any) -> str:
    """从原始 spec 里尽力取 app key（规范化失败时，历史列表也要能显示出 key）。"""
    key = raw.get("key") if isinstance(raw, dict) else None
    return str(key) if key else "?"


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


async def _record_run(
    db: AsyncSession,
    *,
    app_key: str,
    app_name: str | None,
    action: str,
    status: str,
    spec: Any = None,
    summary: str | None = None,
    error: str | None = None,
    duration_ms: int | None = None,
    operator_id: int | None = None,
) -> None:
    """写一条执行历史。**绝不影响主流程**：任何异常都回滚后吞掉。"""
    try:
        db.add(CodegenRun(
            app_key=str(app_key)[:50], app_name=(app_name or None) or None,
            action=action, status=status,
            spec=spec if isinstance(spec, dict) else None,
            summary=summary, error=error,
            duration_ms=duration_ms, operator_id=operator_id,
        ))
        await db.commit()
    except Exception:
        with contextlib.suppress(Exception):
            await db.rollback()


def _run_brief(r: CodegenRun) -> dict:
    return {
        "id": r.id,
        "app_key": r.app_key,
        "app_name": r.app_name,
        "action": r.action,
        "status": r.status,
        "summary": r.summary,
        "duration_ms": r.duration_ms,
        "operator_id": r.operator_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/meta")
async def codegen_meta(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission(READY)),
) -> dict:
    """代码生成页初始化所需元信息。"""
    B = _load_builder()
    asset = B.ASSETS_DIR / B.PLUGIN_HEAD_NAME
    head, head_error = _migration_head()
    installed = (await db.execute(select(InstalledApp.key))).scalars().all()
    sample_path = B.DEFAULT_TEMPLATES_DIR / "spec.sample.yaml"
    return {
        "field_types": sorted(B.FIELD_TYPES),
        "plugin_asset": {
            "exists": asset.exists(),
            "name": B.PLUGIN_HEAD_NAME,
            "size": asset.stat().st_size if asset.exists() else 0,
        },
        "migration_head": head,
        "migration_head_error": head_error,
        "versions_dir": str(ALEMBIC_VERSIONS_DIR),
        "installed_keys": sorted(installed),
        "permissions": {"read": READY, "write": WRITE},
        "sample": sample_path.read_text(encoding="utf-8") if sample_path.exists() else "",
    }


# 生成的模型自带这些列，从已有表导入时默认跳过（避免与模型基建列重名）
MODEL_BUILTIN_COLUMNS = frozenset({"id", "creator_id", "deleted_at", "created_at", "updated_at"})
# 平台内部表，从已有表导入时默认隐藏
_INTERNAL_TABLES = frozenset({"alembic_version", "spatial_ref_sys"})
# PostgreSQL information_schema.data_type → 生成器字段类型
_PG_TYPE_MAP = {
    "integer": "int",
    "bigint": "int",
    "smallint": "int",
    "numeric": "decimal",
    "decimal": "decimal",
    "real": "decimal",
    "double precision": "decimal",
    "boolean": "bool",
    "date": "date",
    "timestamp without time zone": "datetime",
    "timestamp with time zone": "datetime",
    "text": "text",
    "json": "json",
    "jsonb": "json",
}


def _suggest_type(data_type: str) -> str:
    """把 PG 列类型建议为生成器字段类型（字符类型统一走 string + 长度）。"""
    dt = str(data_type or "").lower()
    if dt in ("character varying", "character", "char", "varchar"):
        return "string"
    return _PG_TYPE_MAP.get(dt, "string")


@router.get("/tables")
async def codegen_tables(
    q: str | None = None,
    include_builtin: bool = False,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission(READY)),
) -> dict:
    """列出数据库中的表与列（**只读元数据**），供「从已有表导入」生成 spec。

    只读 information_schema.columns，不触碰任何业务数据。
    默认隐藏平台内部表（alembic_version）与生成模型自带的
    id/creator_id/deleted_at/created_at/updated_at 列；include_builtin=1 可放开。
    """
    rows = (await db.execute(text(
        "SELECT table_name, column_name, data_type, is_nullable,"
        " character_maximum_length, numeric_precision, numeric_scale, column_default"
        " FROM information_schema.columns"
        " WHERE table_schema = 'public'"
        " ORDER BY table_name, ordinal_position"
    ))).mappings().all()

    grouped: dict = {}
    for r in rows:
        tname = r["table_name"]
        if not include_builtin and tname in _INTERNAL_TABLES:
            continue
        grouped.setdefault(tname, []).append({
            "name": r["column_name"],
            "type": r["data_type"],
            "suggested_type": _suggest_type(r["data_type"]),
            "len": r["character_maximum_length"],
            "precision": r["numeric_precision"],
            "scale": r["numeric_scale"],
            "nullable": r["is_nullable"] == "YES",
            "builtin": r["column_name"] in MODEL_BUILTIN_COLUMNS,
            "default": r["column_default"],
        })

    needle = (q or "").strip().lower()
    items = []
    for tname, cols in sorted(grouped.items()):
        usable = cols if include_builtin else [c for c in cols if not c["builtin"]]
        if not usable or (needle and needle not in tname.lower()):
            continue
        items.append({"name": tname, "columns": usable})

    return {"schema": "public", "total": len(items), "items": items}


@router.post("/preview")
async def codegen_preview(
    body: dict,
    _: auth_models.User = Depends(require_permission(WRITE)),
) -> dict:
    """校验 spec 并返回预览：规范化 spec、存档 YAML、文件清单、迁移挂载点。"""
    import yaml

    raw = _read_spec(body)
    got = _generate(raw)
    spec, files = got["spec"], got["files"]
    head, head_error = _migration_head()
    raw_yaml = yaml.safe_dump(raw, allow_unicode=True, sort_keys=False) if isinstance(raw, dict) else ""
    return {
        "ok": True,
        "spec": spec,
        "yaml": raw_yaml,
        "migration_head": head,
        "migration_head_error": head_error,
        "files": [
            {
                "path": p,
                "size": len(c),
                "kind": _KIND.get(Path(p).suffix.lower(), "text"),
            }
            for p, c in sorted(files.items())
        ],
        "total_size": sum(len(c) for c in files.values()),
        "permissions": got["builder"].render_permissions(spec),
        "menu_paths": [e["menu_path"] for e in spec["entities"]],
    }


async def _do_generate(raw: Any, db: AsyncSession, user: auth_models.User) -> Response:
    """生成 ZIP 并留痕（成功 / 失败都写历史）。"""
    t0 = time.perf_counter()
    try:
        got = _generate(raw)
    except HTTPException as exc:
        await _record_run(
            db, app_key=_peek_key(raw), app_name=None, action="generate", status="failed",
            spec=raw, error=str(exc.detail), duration_ms=_ms(t0), operator_id=user.id,
        )
        raise
    spec, files, B = got["spec"], got["files"], got["builder"]
    blob = B.zip_bytes(files)
    filename = "{}-{}.zip".format(spec["key"], spec["version"])
    await _record_run(
        db, app_key=spec["key"], app_name=spec["name"], action="generate", status="ok",
        spec=raw, summary="%d 个文件 · %d 字节" % (len(files), len(blob)),
        duration_ms=_ms(t0), operator_id=user.id,
    )
    return Response(
        content=blob,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/generate")
async def codegen_generate(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission(WRITE)),
) -> Response:
    """生成源码 ZIP 并下载。包根即 App 根（含 manifest.py / __init__.py），可直接安装。"""
    return await _do_generate(_read_spec(body), db, user)


async def _do_install(raw: Any, db: AsyncSession, user: auth_models.User) -> dict:
    """生成并安装到本系统 + 留痕（成功 / 失败都写历史，失败原样抛回让前端贴原文）。"""
    t0 = time.perf_counter()
    try:
        got = _generate(raw)
    except HTTPException as exc:
        await _record_run(
            db, app_key=_peek_key(raw), app_name=None, action="install", status="failed",
            spec=raw, error=str(exc.detail), duration_ms=_ms(t0), operator_id=user.id,
        )
        raise
    spec, files, B = got["spec"], got["files"], got["builder"]
    blob = B.zip_bytes(files)

    from cenkor_admin.apps.system.store_router import install_app_from_zip

    fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="codegen_")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(blob)
        result = await install_app_from_zip(db, spec["key"], Path(tmp_path))
    except Exception as exc:
        await _record_run(
            db, app_key=spec["key"], app_name=spec["name"], action="install", status="failed",
            spec=raw, error=f"{type(exc).__name__}: {exc}",
            duration_ms=_ms(t0), operator_id=user.id,
        )
        raise
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    perms = B.render_permissions(spec)
    menu_paths = [e["menu_path"] for e in spec["entities"]]
    await _record_run(
        db, app_key=spec["key"], app_name=spec["name"], action="install", status="ok",
        spec=raw, summary="%d 个权限 · %d 个菜单" % (len(perms), len(menu_paths)),
        duration_ms=_ms(t0), operator_id=user.id,
    )
    return {
        "ok": True,
        "key": spec["key"],
        "name": spec["name"],
        "version": spec["version"],
        "installed_by": user.id,
        "permissions": perms,
        "menu_paths": menu_paths,
        "note": "已建表并注册菜单/权限（授予 super_admin）。卸载请走应用中心，并重启后端以清除动态路由。",
        **result,
    }


@router.post("/install")
async def codegen_install(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission(WRITE)),
) -> dict:
    """生成并**安装到本系统**：解压到 apps/<key> → 前端资源 → 迁移 upgrade →
    注册权限/菜单（含 super_admin）→ 动态注册 API 路由。**无需重启后端**。

    仅应由管理员在代码生成页显式确认后调用（安装会建表、注册菜单与权限）。
    """
    return await _do_install(_read_spec(body), db, user)


# ---------------------------------------------------------------------------
# 执行历史端点
# ---------------------------------------------------------------------------

@router.get("/runs")
async def codegen_runs(
    limit: int = 30,
    app_key: str | None = None,
    action: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission(READY)),
) -> dict:
    """执行历史列表（只给摘要，spec 快照走 /runs/{id}）。"""
    stmt = select(CodegenRun).order_by(CodegenRun.created_at.desc(), CodegenRun.id.desc())
    if app_key:
        stmt = stmt.where(CodegenRun.app_key == app_key)
    if action:
        stmt = stmt.where(CodegenRun.action == action)
    rows = (await db.execute(stmt.limit(max(1, min(limit, 200))))).scalars().all()
    return {"total": len(rows), "items": [_run_brief(r) for r in rows]}


@router.get("/runs/{run_id}")
async def codegen_run_detail(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission(READY)),
) -> dict:
    """执行详情：当时的 spec 快照（可直接再次执行）与失败时的原始报错。"""
    run = await db.get(CodegenRun, run_id)
    if run is None:
        raise HTTPException(404, "执行记录不存在")
    return {"ok": True, **_run_brief(run), "spec": run.spec, "error": run.error}


@router.post("/runs/{run_id}/rerun")
async def codegen_run_rerun(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission(WRITE)),
) -> Any:
    """按历史记录再次执行：generate → 下载 ZIP；install → 重新安装（会覆盖同名 App）。"""
    run = await db.get(CodegenRun, run_id)
    if run is None:
        raise HTTPException(404, "执行记录不存在")
    if not isinstance(run.spec, dict) or not run.spec:
        raise HTTPException(400, "该记录没有可用的 spec 快照，无法再次执行")
    if run.action == "install":
        return await _do_install(run.spec, db, user)
    return await _do_generate(run.spec, db, user)


@router.delete("/runs/{run_id}")
async def codegen_run_delete(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission(WRITE)),
) -> dict:
    """删除一条历史记录（只删留痕，不影响已安装的 App 与其数据表）。"""
    run = await db.get(CodegenRun, run_id)
    if run is None:
        raise HTTPException(404, "执行记录不存在")
    await db.delete(run)
    await db.commit()
    return {"ok": True, "id": run_id}
