"""P2-1 静态包导出 / P2-2 CDN 刷新 的 HTTP 入口。"""

from __future__ import annotations

import asyncio
import io
import sys
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms import cdn_service, models, static_cache
from cenkor_admin.core.db import get_db
from cenkor_admin.core.site_scope import require_site_id

router = APIRouter(prefix="/delivery", tags=["cms-delivery"])
# apps/cms/export_router.py -> parents[4] 才是 backend/
BACKEND_ROOT = Path(__file__).resolve().parents[4]


def _host_of(domain: str | None) -> str:
    return (domain or "").strip().lower()


@router.get("/static/stats", summary="静态缓存现状")
async def static_stats(
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    site_id = require_site_id()
    domain = await static_cache.site_domain(db, site_id)
    st = static_cache.stats(_host_of(domain) or None)
    return {
        "enabled": static_cache.cache_enabled(),
        "root": str(static_cache.cache_root()),
        "domain": domain,
        **st,
    }


@router.get("/static/package", summary="导出静态包（zip，可直接丢 CDN / 对象存储）")
async def static_package(
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> StreamingResponse:
    site_id = require_site_id()
    domain = await static_cache.site_domain(db, site_id)
    host = _host_of(domain)
    root = static_cache.cache_root()
    target = root / host if host else root
    if not target.is_dir():
        raise HTTPException(
            404,
            f"没有可导出的静态文件（缓存根 {root}，站点目录 {host or '未绑定域名'}）。"
            "先在宝塔环境变量开 CMS_STATIC_CACHE=1 并访问几个页面预热。",
        )
    files = [p for p in target.rglob("*.html") if p.is_file()]
    if not files:
        raise HTTPException(404, f"{target} 下没有 html，缓存还没热起来")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in files:
            zf.write(p, p.relative_to(target).as_posix())
    size = buf.tell()
    buf.seek(0)
    name = f"{host or 'site'}-static-{site_id}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Package-Files": str(len(files)),
            "X-Package-Bytes": str(size),
        },
    )


class WarmIn(BaseModel):
    base_url: str = ""


@router.post("/static/warm", summary="按 sitemap 预热静态文件")
async def static_warm(
    body: WarmIn,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    site_id = require_site_id()
    base = body.base_url.strip()
    if not base:
        domain = await static_cache.site_domain(db, site_id)
        if not domain:
            raise HTTPException(422, "站点未绑定域名，请传 base_url")
        base = f"https://{domain}"
    if not base.startswith(("http://", "https://")):
        raise HTTPException(422, "base_url 必须以 http(s) 开头")

    script = BACKEND_ROOT / "scripts" / "build_static_cache.py"
    if not script.is_file():
        raise HTTPException(500, f"预热脚本不存在：{script}")
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script),
            "--warm",
            base,
            cwd=str(BACKEND_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=240)
    except TimeoutError:
        return {"ok": False, "base_url": base, "message": "预热超过 240s，已放弃等待（脚本仍在后台跑）"}
    text = (out or b"").decode("utf-8", "replace")
    return {"ok": proc.returncode == 0, "base_url": base, "output": text[-2000:]}


# ---------------------------------------------------------------- CDN


class CdnConfIn(BaseModel):
    provider: str = ""
    zone_id: str = ""
    token: str = ""
    webhook_url: str = ""
    webhook_secret: str = ""
    keep_token: bool = True
    keep_webhook_secret: bool = True


class CdnPurgeIn(BaseModel):
    urls: list[str] = Field(default_factory=list, max_length=1000)
    purge_all: bool = False


@router.get("/cdn/config", summary="读 CDN 配置（密钥不回明文）")
async def cdn_config(
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    site_id = require_site_id()
    site, conf = await cdn_service.load_conf(db, site_id)
    if site is None:
        raise HTTPException(404, "站点不存在")
    return cdn_service.public_conf(conf)


@router.put("/cdn/config", summary="存 CDN 配置")
async def cdn_config_save(
    body: CdnConfIn,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    site_id = require_site_id()
    patch = body.model_dump()
    if not body.provider:
        patch["provider"] = "off"
    try:
        return await cdn_service.save_conf(db, site_id, patch)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/cdn/purge", summary="刷新 CDN 缓存")
async def cdn_purge(
    body: CdnPurgeIn,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    site_id = require_site_id()
    res = await cdn_service.purge(db, site_id, body.urls, purge_all=body.purge_all)
    if not res["ok"]:
        raise HTTPException(502, f"{res['provider']}: {res['message']}")
    return res
