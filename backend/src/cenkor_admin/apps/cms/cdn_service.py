"""CDN 刷新：Cloudflare 官方 API + 通用 webhook。

配置存站点 `settings["cdn"]`（每站独立）：
    {"provider": "cloudflare|webhook|off", "zone_id": "...", "token": "...",
     "webhook_url": "...", "webhook_secret": "..."}
七牛/又拍的刷新接口签名各家不同，统一走 webhook 中转，不在代码里硬编码各家 SDK。
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import models

CF_URL = "https://api.cloudflare.com/client/v4/zones/{zone}/purge_cache"
MASK = "••••"


def _site_settings(site: models.Site) -> dict[str, Any]:
    return dict(site.settings or {}) if isinstance(site.settings, dict) else {}


async def load_conf(db: AsyncSession, site_id: int) -> tuple[models.Site | None, dict[str, Any]]:
    site = (await db.execute(select(models.Site).where(models.Site.id == site_id))).scalars().first()
    if site is None:
        return None, {}
    return site, dict(_site_settings(site).get("cdn") or {})


def public_conf(conf: dict[str, Any]) -> dict[str, Any]:
    """回给前端的东西：密钥只报有没有，不回明文。"""
    return {
        "provider": conf.get("provider") or "off",
        "zone_id": conf.get("zone_id") or "",
        "has_token": bool(conf.get("token")),
        "webhook_url": conf.get("webhook_url") or "",
        "has_webhook_secret": bool(conf.get("webhook_secret")),
    }


async def save_conf(db: AsyncSession, site_id: int, patch: dict[str, Any]) -> dict[str, Any]:
    site, conf = await load_conf(db, site_id)
    if site is None:
        raise ValueError("站点不存在")
    keep_secret = patch.pop("keep_token", False)
    keep_hook = patch.pop("keep_webhook_secret", False)
    for k in ("provider", "zone_id", "webhook_url"):
        if k in patch:
            conf[k] = (patch[k] or "").strip() if isinstance(patch[k], str) else patch[k]
    if "token" in patch and (patch["token"] or not keep_secret):
        conf["token"] = (patch["token"] or "").strip()
    if "webhook_secret" in patch and (patch["webhook_secret"] or not keep_hook):
        conf["webhook_secret"] = (patch["webhook_secret"] or "").strip()
    settings = _site_settings(site)
    settings["cdn"] = conf
    site.settings = settings
    await db.commit()
    return public_conf(conf)


async def purge(
    db: AsyncSession, site_id: int, urls: list[str], *, purge_all: bool = False
) -> dict[str, Any]:
    """刷新缓存。返回 {ok, provider, message, purged}。永不抛，失败原因照实回。"""
    _site, conf = await load_conf(db, site_id)
    provider = (conf.get("provider") or "off").strip().lower()
    if provider in ("", "off"):
        return {"ok": False, "provider": "off", "message": "未配置 CDN，站点设置里先选提供商", "purged": 0}

    urls = [u.strip() for u in urls if u and u.strip().startswith("http")][:1000]
    if not urls and not purge_all:
        return {"ok": False, "provider": provider, "message": "urls 为空", "purged": 0}

    try:
        if provider == "cloudflare":
            zone, token = (conf.get("zone_id") or "").strip(), (conf.get("token") or "").strip()
            if not zone or not token:
                return {"ok": False, "provider": provider, "message": "缺 zone_id 或 token", "purged": 0}
            body: dict[str, Any] = {"purge_everything": True} if purge_all else {"files": urls}
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    CF_URL.format(zone=zone),
                    headers={"Authorization": f"Bearer {token}"},
                    json=body,
                )
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            ok = resp.status_code < 400 and bool(data.get("success", True))
            msg = "" if ok else str(data.get("errors") or resp.text[:200])
            return {"ok": ok, "provider": provider, "message": msg, "purged": len(urls)}

        if provider == "webhook":
            hook = (conf.get("webhook_url") or "").strip()
            if not hook:
                return {"ok": False, "provider": provider, "message": "缺 webhook_url", "purged": 0}
            headers = {"Content-Type": "application/json"}
            secret = (conf.get("webhook_secret") or "").strip()
            if secret:
                headers["X-CDN-Secret"] = secret
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    hook, headers=headers, json={"site_id": site_id, "urls": urls, "all": purge_all}
                )
            ok = resp.status_code < 400
            return {
                "ok": ok,
                "provider": provider,
                "message": "" if ok else f"HTTP {resp.status_code}: {resp.text[:200]}",
                "purged": len(urls),
            }

        return {
            "ok": False,
            "provider": provider,
            "message": f"未实现的提供商 {provider}，请用 webhook 中转",
            "purged": 0,
        }
    except Exception as exc:
        # 宽泛捕获是有意的：网络超时、签名错误、上游 5xx 都统一降级成原因回显，
        # 由调用方决定重试，避免刷新缓存失败连带整个保存流程报错。
        return {"ok": False, "provider": provider, "message": str(exc)[:200], "purged": 0}
