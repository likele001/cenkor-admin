"""应用市场 API（开源层实现）

与「应用商店」（``store_router``，管理开发者提交的应用包）不同，本模块面向
**官方应用市场**：浏览官方云的公开目录，一键安装 / 升级官方应用。

对齐 FastAdmin / iCMS 插件中心的做法：

* 目录数据**实时取自官方云**，本地不存商品数据 —— 全新部署也能看到全部应用，
  不再依赖 seed 往本地灌数据；
* 官方公开目录**无需登录**即可读取，浏览永远可用；
* 安装分两类：本地已有代码的（免费 / 内置应用）直接走系统安装，不需要下载包；
  本地没有代码的（付费商业应用）凭授权码从官方下载授权包再解压安装；
* **无状态**：授权码与实例令牌由前端保存、随请求携带，服务端不落库、不引入迁移。
  商业版另有闭源的 ``commerce`` / ``cloud_router`` 链路，自带库表与授权体系。
"""
from __future__ import annotations

import hashlib
import os
import socket
import tempfile
import time
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.system.models import InstalledApp
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.db import get_db

log = structlog.get_logger()
router = APIRouter()

MARKET_TIMEOUT = 30.0        # 目录 / 详情类请求
PACKAGE_TIMEOUT = 300.0      # 应用包下载（可能几十 MB）
CATALOG_PAGE_SIZE = 100      # 官方目录单页上限
CATALOG_MAX_PAGES = 10       # 最多翻 10 页，防官方分页异常时死循环
CATALOG_TTL_SECONDS = 60     # 目录内存缓存，避免每次进页面都打官方云

_CATALOG_CACHE: dict[str, Any] = {"at": 0.0, "items": None}


# ============================================================
# 工具
# ============================================================

def _hub_base() -> str:
    """官方应用市场地址：优先 MARKET_HUB_URL，回退 PORTAL_PUBLIC_URL。"""
    s = get_settings()
    base = (getattr(s, "MARKET_HUB_URL", "") or s.PORTAL_PUBLIC_URL or "").rstrip("/")
    if not base:
        raise HTTPException(503, "未配置官方应用市场地址（MARKET_HUB_URL）")
    return base


def _instance_fp() -> str:
    """实例指纹：绑定官方账号时上报，官方据此区分不同实例。

    开源层不依赖闭源的 licensing 模块，用「主机名 + 对外地址」派生，同一实例稳定。
    """
    raw = f"{socket.gethostname()}|{get_settings().PUBLIC_BASE_URL or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _is_free(price: Any) -> bool:
    """价格未启用（或没有价格记录）= 免费应用。"""
    if not isinstance(price, dict):
        return True
    return not price.get("enabled")


def _ver_tuple(v: Any) -> tuple:
    parts = []
    for seg in str(v or "").split("."):
        seg = seg.strip()
        parts.append(int(seg) if seg.isdigit() else 0)
    return tuple(parts)


def _ver_gt(a: Any, b: Any) -> bool:
    return _ver_tuple(a) > _ver_tuple(b)


async def _hub_get(
    path: str,
    params: dict | None = None,
    timeout: float = MARKET_TIMEOUT,
    headers: dict | None = None,
):
    import httpx

    hub = _hub_base()
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            return await client.get(f"{hub}{path}", params=params, headers=headers or {})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"官方应用市场不可达：{e}") from e


async def _hub_post(path: str, payload: dict | None = None, headers: dict | None = None):
    import httpx

    hub = _hub_base()
    try:
        async with httpx.AsyncClient(timeout=MARKET_TIMEOUT, follow_redirects=True) as client:
            return await client.post(f"{hub}{path}", json=payload or {}, headers=headers or {})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"官方应用市场不可达：{e}") from e


def _hub_detail(resp, fallback: str) -> str:
    """把官方返回的错误体转成一句可读文案。"""
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return (resp.text or fallback)[:300]
    if isinstance(data, dict) and data.get("detail"):
        detail = data["detail"]
        if isinstance(detail, list):  # FastAPI 校验错误
            return str(detail[0].get("msg") if detail else fallback)[:300]
        return str(detail)[:300]
    return fallback


# ============================================================
# 目录
# ============================================================

async def _fetch_catalog(force: bool = False) -> list[dict[str, Any]]:
    """拉取官方公开目录（带短 TTL 内存缓存）。"""
    now = time.time()
    cached = _CATALOG_CACHE.get("items")
    if (
        not force
        and cached is not None
        and now - float(_CATALOG_CACHE.get("at") or 0.0) < CATALOG_TTL_SECONDS
    ):
        return cached

    items: list[dict[str, Any]] = []
    for page in range(1, CATALOG_MAX_PAGES + 1):
        resp = await _hub_get(
            "/api/v1/store/apps", {"page": page, "page_size": CATALOG_PAGE_SIZE}
        )
        if resp.status_code != 200:
            raise HTTPException(502, f"官方应用市场返回异常（HTTP {resp.status_code}）")
        try:
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"官方应用市场返回了非 JSON 内容：{e}") from e
        batch = data.get("items") or data.get("data") or []
        if not isinstance(batch, list):
            break
        items.extend(x for x in batch if isinstance(x, dict))
        if len(batch) < CATALOG_PAGE_SIZE:
            break

    _CATALOG_CACHE["at"] = now
    _CATALOG_CACHE["items"] = items
    return items


async def _local_state(
    db: AsyncSession,
) -> tuple[dict[str, Any], dict[str, InstalledApp]]:
    """本地「有代码的 App」与「已装状态」，用于和官方目录做比对。"""
    from cenkor_admin.apps.system.app_registry import scan_app_manifests

    manifests = scan_app_manifests()
    rows = (await db.execute(select(InstalledApp))).scalars().all()
    installed = {str(r.key): r for r in rows}
    return manifests, installed


def _decorate(
    item: dict[str, Any],
    manifests: dict[str, Any],
    installed: dict[str, InstalledApp],
) -> dict[str, Any]:
    """把官方目录条目与本地状态合并成前端直接可用的一行。"""
    key = str(item.get("key") or item.get("app_key") or "")
    manifest = manifests.get(key)
    row = installed.get(key)

    installed_version = None
    if row is not None and getattr(row, "status", "installed") == "installed":
        installed_version = str(row.version or "") or None
    remote_version = str(item.get("version") or "") or None
    price = item.get("price")

    return {
        "key": key,
        "name": item.get("name") or (manifest.name if manifest is not None else key),
        "version": remote_version,
        "summary": item.get("summary") or item.get("description") or "",
        "description": item.get("description") or "",
        "icon": item.get("icon") or "",
        "category": item.get("category") or "other",
        "category_label": item.get("category_label") or "",
        "author": item.get("author") or "",
        "updated_at": item.get("updated_at"),
        "price": price,
        "is_free": _is_free(price),
        "has_local_code": manifest is not None,
        "install_mode": "system" if manifest is not None else "package",
        "installed": installed_version is not None,
        "enabled": bool(getattr(row, "enabled", False)) if row is not None else False,
        "installed_version": installed_version,
        "has_update": bool(
            installed_version
            and remote_version
            and _ver_gt(remote_version, installed_version)
        ),
    }


@router.get("/status")
async def market_status(
    _: Any = Depends(require_permission("rbac:role:write")),
):
    """官方市场可用性：前端据此决定显示市场还是引导离线安装。"""
    hub = _hub_base()
    reachable = False
    total = 0
    error = None
    try:
        items = await _fetch_catalog()
        total = len(items)
        reachable = True
    except HTTPException as e:  # noqa: BLE001
        error = e.detail

    return {
        "hub": hub,
        "reachable": reachable,
        "catalog_count": total,
        "instance_uid": _instance_fp(),
        "portal_url": hub,
        "connect_url": f"{hub}/connect",
        "error": error,
    }


@router.get("/catalog")
async def market_catalog(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    category: str = Query(""),
    q: str = Query(""),
    filter: str = Query("", description="free | paid | installed | update"),
    refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(require_permission("rbac:role:write")),
):
    """官方应用目录（实时取官方云 + 本地已装状态）。"""
    manifests, installed = await _local_state(db)
    raw = await _fetch_catalog(force=refresh)
    all_items = [_decorate(it, manifests, installed) for it in raw]

    # 分类聚合基于全量，不受当前筛选影响
    cats: dict[str, dict[str, Any]] = {}
    for it in all_items:
        c = str(it["category"])
        entry = cats.setdefault(
            c, {"value": c, "label": it["category_label"] or c, "count": 0}
        )
        entry["count"] += 1
    categories = sorted(cats.values(), key=lambda x: (-x["count"], x["value"]))

    items = all_items
    if category:
        items = [it for it in items if it["category"] == category]
    if filter == "free":
        items = [it for it in items if it["is_free"]]
    elif filter == "paid":
        items = [it for it in items if not it["is_free"]]
    elif filter == "installed":
        items = [it for it in items if it["installed"]]
    elif filter == "update":
        items = [it for it in items if it["has_update"]]
    if q.strip():
        kw = q.strip().lower()
        items = [
            it
            for it in items
            if kw in it["key"].lower()
            or kw in str(it["name"]).lower()
            or kw in str(it["summary"]).lower()
        ]

    total = len(items)
    start = (page - 1) * page_size
    return {
        "items": items[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "hub": _hub_base(),
        "categories": categories,
        "stats": {
            "all": len(all_items),
            "free": sum(1 for x in all_items if x["is_free"]),
            "paid": sum(1 for x in all_items if not x["is_free"]),
            "installed": sum(1 for x in all_items if x["installed"]),
            "updates": sum(1 for x in all_items if x["has_update"]),
        },
    }


@router.get("/updates")
async def market_updates(
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(require_permission("rbac:role:write")),
):
    """本地已装应用与官方最新版本的差异清单。"""
    manifests, installed = await _local_state(db)
    raw = await _fetch_catalog()
    out: list[dict[str, Any]] = []
    for it in raw:
        d = _decorate(it, manifests, installed)
        if d["has_update"]:
            out.append({
                "key": d["key"],
                "name": d["name"],
                "local_version": d["installed_version"],
                "remote_version": d["version"],
                "has_local_code": d["has_local_code"],
                "is_free": d["is_free"],
            })
    return {"items": out, "count": len(out)}


@router.get("/apps/{app_key}")
async def market_app_detail(
    app_key: str,
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(require_permission("rbac:role:write")),
):
    """应用详情：官方目录里的信息 + 本地状态与安装建议。"""
    raw = await _fetch_catalog()
    entry = next(
        (it for it in raw if str(it.get("key") or it.get("app_key")) == app_key), None
    )
    if entry is None:
        resp = await _hub_get(f"/api/v1/store/apps/{app_key}")
        if resp.status_code != 200:
            raise HTTPException(404, f"官方市场没有应用 {app_key}")
        entry = resp.json()

    manifests, installed = await _local_state(db)
    detail = _decorate(entry, manifests, installed)
    detail["highlights"] = entry.get("highlights") or []
    detail["screenshots"] = entry.get("screenshots") or []
    detail["permissions"] = entry.get("permissions") or []
    detail["versions"] = entry.get("versions") or []
    detail["developer"] = entry.get("developer") or {}
    detail["has_frontend"] = bool(entry.get("has_frontend"))
    if detail["has_local_code"]:
        detail["install_hint"] = "本地已自带该应用代码，点安装即可启用或恢复。"
    elif detail["is_free"]:
        detail["install_hint"] = "免费应用，安装时会自动向官方取包。"
    else:
        detail["install_hint"] = "付费应用，请在官方门户购买后把授权码填进来安装。"
    return detail


# ============================================================
# 安装 / 升级
# ============================================================

async def _download_package(app_key: str, license_key: str) -> Path:
    """从官方下载授权包到临时文件，返回路径（调用方负责删除）。"""
    hub = _hub_base()
    import httpx

    try:
        async with httpx.AsyncClient(timeout=PACKAGE_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(
                f"{hub}/api/v1/store/cloud/packages/{app_key}",
                params={"license_key": license_key},
            )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"下载应用包失败：{e}") from e

    if resp.status_code == 404:
        raise HTTPException(404, "授权码无效，或该应用暂无可分发的安装包")
    if resp.status_code == 403:
        raise HTTPException(403, _hub_detail(resp, "授权码与该应用不匹配"))
    if resp.status_code != 200:
        code = resp.status_code if resp.status_code < 500 else 502
        raise HTTPException(code, f"下载应用包失败：{_hub_detail(resp, resp.text[:200])}")

    content = resp.content
    if content[:2] != b"PK":
        raise HTTPException(502, "官方返回的不是有效的 ZIP 应用包")

    fd, path = tempfile.mkstemp(suffix=".zip")
    with os.fdopen(fd, "wb") as f:
        f.write(content)
    return Path(path)


@router.post("/install")
async def market_install(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(require_permission("rbac:role:write")),
):
    """安装 / 升级官方应用。

    * 本地已有代码（免费、内置应用）→ 系统安装，不需要授权码、不解压 ZIP；
    * 本地没有代码（官方分发的商业应用）→ 凭授权码从官方拉包解压安装。
    """
    app_key = str(body.get("app_key") or body.get("key") or "").strip()
    license_key = str(body.get("license_key") or "").strip()
    if not app_key:
        raise HTTPException(400, "app_key 必填")

    from cenkor_admin.apps.system.app_registry import install_app, scan_app_manifests

    manifests = scan_app_manifests()
    if app_key in manifests:
        try:
            row = await install_app(db, app_key)
            await db.commit()
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        log.info("market.installed_system", app_key=app_key, by=user.id)
        return {
            "ok": True,
            "app_key": app_key,
            "mode": "system",
            "version": row.version,
            "has_frontend": bool(row.has_frontend),
            "warnings": [],
        }

    if not license_key:
        raise HTTPException(
            400,
            "该应用由官方分发，需要授权码：请先在官方门户购买，再把授权码填入此处",
        )

    tmp_path = await _download_package(app_key, license_key)
    try:
        from cenkor_admin.apps.system.store_router import install_app_from_zip

        result = await install_app_from_zip(db, app_key, tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    log.info("market.installed_package", app_key=app_key, by=user.id)
    return {"ok": True, "app_key": app_key, "mode": "package", **result}


# ============================================================
# 官方账号绑定（device code 流；令牌由前端保存，服务端无状态）
# ============================================================

@router.post("/bind/start")
async def market_bind_start(
    body: dict = Body(default={}),
    _: Any = Depends(require_permission("rbac:role:write")),
):
    """申请一次性绑定码：拿到 user_code 后去官方门户确认。"""
    s = get_settings()
    name = str(body.get("instance_name") or "").strip()[:120] or (
        f"{socket.gethostname()} · cenkor-admin"
    )
    resp = await _hub_post(
        "/api/v1/store/public/cloud/device/start",
        {
            "instance_name": name,
            "instance_url": str(body.get("instance_url") or s.PUBLIC_BASE_URL or "")[:255],
            "instance_uid": _instance_fp(),
        },
    )
    if resp.status_code != 200:
        raise HTTPException(502, f"申请绑定码失败：{_hub_detail(resp, resp.text[:200])}")
    out = dict(resp.json() or {})
    out["hub"] = _hub_base()
    return out


@router.post("/bind/poll")
async def market_bind_poll(
    body: dict = Body(...),
    _: Any = Depends(require_permission("rbac:role:write")),
):
    """轮询绑定结果；approved 后返回实例令牌，交由前端保存。"""
    device_code = str(body.get("device_code") or "").strip()
    if not device_code:
        raise HTTPException(400, "device_code 必填")
    resp = await _hub_post(
        "/api/v1/store/public/cloud/device/poll", {"device_code": device_code}
    )
    if resp.status_code != 200:
        raise HTTPException(502, f"轮询绑定结果失败：{_hub_detail(resp, resp.text[:200])}")
    data = dict(resp.json() or {})
    if data.get("status") == "approved" and not data.get("instance_token"):
        raise HTTPException(502, "官方云未返回实例令牌")
    return data


@router.post("/purchases")
async def market_purchases(
    body: dict = Body(default={}),
    _: Any = Depends(require_permission("rbac:role:write")),
):
    """本账号已购列表（前端携带实例令牌，服务端只做转发）。"""
    token = str(body.get("instance_token") or body.get("token") or "").strip()
    if not token:
        raise HTTPException(400, "缺少实例令牌，请先绑定官方账号")
    resp = await _hub_get(
        "/api/v1/store/cloud/my-purchases",
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code == 401:
        raise HTTPException(401, "实例令牌已失效，请重新绑定官方账号")
    if resp.status_code != 200:
        raise HTTPException(
            502, f"取已购列表失败（HTTP {resp.status_code}）：{resp.text[:200]}"
        )
    try:
        return resp.json()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"官方返回了非 JSON 内容：{e}") from e
