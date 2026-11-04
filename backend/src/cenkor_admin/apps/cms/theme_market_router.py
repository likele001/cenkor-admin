"""模板市场 API —— 站长浏览/安装第三方主题。

与「模板工作室」（在线编辑）互补：这里只管**装**，装完去工作室改。
目录实时取自官方云（market_router），本地只存已装状态（cms_templates）。

三个端点：

| 端点 | 作用 |
|---|---|
| ``GET /cms/theme-market/catalog`` | 浏览主题（过滤 dev_method=theme） |
| ``POST /cms/theme-market/install`` | 安装主题（免费/付费） |
| ``GET /cms/theme-market/installed`` | 已装主题列表（含可更新提示） |
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.cms import builtin_theme, models, theme_package
from cenkor_admin.core.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


async def _installed_themes_map(db: AsyncSession, site_id: int) -> dict[str, dict[str, Any]]:
    """已装主题 → {theme_name: {version, settings_count, ...}}。"""
    rows = (await db.execute(
        select(models.CmsTemplate.theme, models.CmsTemplate.path, models.CmsTemplate.content)
        .where(models.CmsTemplate.site_id == site_id)
    )).all()

    themes: dict[str, dict[str, Any]] = {}
    for theme, path, content in rows:
        info = themes.setdefault(theme, {"files": 0, "manifest": None})
        info["files"] += 1
        if path == theme_package.MANIFEST_NAME:
            try:
                manifest = theme_package.manifest_from_json(content, legacy_key=theme)
                info["manifest"] = manifest
            except Exception:
                pass

    return themes


@router.get("/theme-market/catalog")
async def theme_market_catalog(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    q: str = Query(""),
    site_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(require_permission("cms:site:read")),
):
    """浏览主题市场（过滤 dev_method=theme，合并本地已装状态）。"""
    from cenkor_admin.apps.system.market_router import (
        _decorate,
        _fetch_catalog,
        _local_state,
    )

    manifests, installed = await _local_state(db)
    raw = await _fetch_catalog()
    all_items = [_decorate(it, manifests, installed) for it in raw]

    # 只留主题包
    items = [it for it in all_items if it.get("dev_method") == "theme"]

    # 关键词搜索
    if q.strip():
        kw = q.strip().lower()
        items = [
            it for it in items
            if kw in it["key"].lower()
            or kw in str(it["name"]).lower()
            or kw in str(it["summary"]).lower()
        ]

    # 合并本地已装状态（主题装在 cms_templates，不在 InstalledApp）
    local_themes = await _installed_themes_map(db, site_id)
    for it in items:
        local = local_themes.get(it["key"])
        if local:
            manifest = local.get("manifest")
            it["installed"] = True
            it["installed_version"] = manifest.version if manifest else None
            it["local_files"] = local["files"]
        else:
            it["installed"] = False
            it["installed_version"] = None
            it["local_files"] = 0

    total = len(items)
    start = (page - 1) * page_size
    return {
        "items": items[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/theme-market/install")
async def theme_market_install(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(require_permission("cms:site:write")),
):
    """安装主题（免费/付费）。

    免费主题不需要授权码；付费主题需要 license_key。
    """


    app_key = str(body.get("app_key") or body.get("key") or "").strip()
    license_key = str(body.get("license_key") or "").strip()
    site_id = int(body.get("site_id") or 1)
    activate = bool(body.get("activate", False))

    if not app_key:
        raise HTTPException(400, "app_key 必填")

    # 直接走主题安装逻辑（不经过 market_install，避免权限依赖）
    from cenkor_admin.apps.cms import theme_install as _ti
    from cenkor_admin.apps.cms import theme_package as _tp

    # 免费主题：不需要授权码
    if not license_key:
        from cenkor_admin.apps.system.market_router import _download_free_package

        try:
            tmp_path, _hub_product, _hub_dev_method = await _download_free_package(app_key)
        except HTTPException as e:
            if e.status_code == 403:
                raise HTTPException(
                    400,
                    "该主题需要授权码：请先在官方门户购买，再把授权码填入此处",
                ) from e
            raise
    else:
        from cenkor_admin.apps.system.market_router import _download_package

        tmp_path, _hub_product, _hub_dev_method = await _download_package(app_key, license_key)

    try:
        raw = Path(tmp_path).read_bytes()
        try:
            raw_files, too_big = _ti.unzip_theme_package(raw)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        check = _tp.validate_package(raw_files, expected_key=app_key, require_manifest=True)
        errors = too_big + check.errors
        if errors:
            raise HTTPException(
                400,
                {"message": f"{len(errors)} 个文件未通过校验，已整体拒绝",
                 "errors": errors, "warnings": check.warnings},
            )

        result = await _ti.install_theme_files(
            db, site_id=site_id, theme=app_key, files=dict(check.files), overwrite=True
        )
        manifest = check.manifest
    finally:
        import contextlib
        import os
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)

    # 可选：安装后立即切换为生效主题
    if activate:
        from cenkor_admin.apps.cms import models as cms_models

        site_row = (await db.execute(
            select(cms_models.Site).where(cms_models.Site.id == site_id)
        )).scalars().first()
        if site_row:
            settings = dict(site_row.settings or {})
            settings["cms.theme"] = app_key
            site_row.settings = settings
            await db.commit()

    return {
        "ok": True,
        "app_key": app_key,
        "mode": "theme",
        "site_id": site_id,
        "written": result["written"],
        "skipped": result["skipped"],
        "warnings": check.warnings,
        "manifest": {
            "name": manifest.name if manifest else app_key,
            "version": manifest.version if manifest else None,
            "settings_count": len(manifest.settings) if manifest else 0,
        },
    }


@router.get("/theme-market/installed")
async def theme_market_installed(
    site_id: int = Query(1),
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(require_permission("cms:site:read")),
):
    """已装主题列表（含内置主题）。"""
    local_themes = await _installed_themes_map(db, site_id)

    out = []
    for theme_name, info in local_themes.items():
        manifest = info.get("manifest")
        out.append({
            "theme": theme_name,
            "name": manifest.name if manifest else theme_name,
            "version": manifest.version if manifest else None,
            "description": manifest.description if manifest else "",
            "settings_count": len(manifest.settings) if manifest else 0,
            "widgets_count": len(manifest.widgets) if manifest else 0,
            "files": info["files"],
            "source": "db",
        })

    # 内置主题也列出来
    for name in builtin_theme.list_builtin_themes():
        if name not in local_themes:
            out.append({
                "theme": name,
                "name": name,
                "version": None,
                "description": "内置主题",
                "settings_count": 0,
                "widgets_count": 0,
                "files": len(builtin_theme.BUILTIN_THEMES.get(name, {})),
                "source": "builtin",
            })

    return {"items": out, "total": len(out)}
