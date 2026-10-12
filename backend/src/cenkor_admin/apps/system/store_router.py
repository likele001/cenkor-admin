"""应用商店 API"""
from __future__ import annotations

import hashlib
import json
import io
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.portal import models as portal_models
from cenkor_admin.apps.system import pricing_bridge
from cenkor_admin.apps.system import pricing_rules
from cenkor_admin.apps.system import store_models
from cenkor_admin.apps.system.models import InstalledApp
from cenkor_admin.apps.system.showcase_meta import SHOWCASE
from cenkor_admin.core import hooks
from cenkor_admin.core.db import get_db
from cenkor_admin.core.security import decode_token
from cenkor_admin.core.storage import s3
from cenkor_admin.apps.portal.auth import decode_portal_token, is_portal_token, PORTAL_JWT_ISSUER

log = structlog.get_logger()
router = APIRouter()
security = HTTPBearer(auto_error=False)

APPS_DIR = Path(__file__).resolve().parent.parent
# 外置应用目录：`cenkor_admin/apps/__init__.py` 把它追加进包的 ``__path__``，
# 于是 `import cenkor_admin.apps.<key>` 在两处都能解析到同名应用。
EXTERNAL_APPS_DIR = APPS_DIR.parent.parent / "apps"
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent.parent / "uploads" / "apps"
# 前端静态资源目录（与 main.py 中的挂载点一致）
FRONTEND_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "apps"

# 上传与解压安全上限（防超大包 / zip bomb / 路径穿越写出目标目录）
MAX_APP_UPLOAD_BYTES = 200 * 1024 * 1024      # 上传压缩包 ≤ 200MB
MAX_ZIP_ENTRIES = 10_000                       # ZIP 内条目数上限
MAX_ZIP_FILE_SIZE = 200 * 1024 * 1024          # 单文件解压后 ≤ 200MB
MAX_ZIP_TOTAL_SIZE = 1024 * 1024 * 1024        # 解压总大小 ≤ 1GB


async def require_portal_or_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """支持 portal token 或 admin token 的鉴权"""
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    security_bearer = HTTPBearer(auto_error=False)

    if not creds or not creds.credentials:
        raise HTTPException(401, "未提供认证信息")

    # 尝试 admin token
    try:
        payload = decode_token(creds.credentials)
        if payload.get("type") == "access" and not is_portal_token(payload):
            user_id = int(payload["sub"])
            user = await db.get(auth_models.User, user_id)
            if user and user.status == "active":
                return {"user_type": "admin", "user_id": user_id, "user": user}
    except Exception:
        pass

    # 尝试 portal token
    try:
        portal_payload = decode_portal_token(creds.credentials)
        if portal_payload.get("iss") == PORTAL_JWT_ISSUER and portal_payload.get("type") == "access":
            user_id = int(portal_payload["sub"])
            user = await db.get(portal_models.PortalUser, user_id)
            if user and user.status == "active" and not user.deleted_at:
                return {"user_type": "portal", "user_id": user_id, "user": user}
    except Exception:
        pass

    raise HTTPException(401, "Token 无效")


# ============================================================
# 开发者管理
# ============================================================

@router.get("/developers", response_model=dict[str, Any])
async def list_developers(
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:read")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    stmt = select(store_models.Developer).order_by(store_models.Developer.id.desc())
    count = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return {
        "items": [
            {"id": d.id, "user_id": d.user_id, "display_name": d.display_name,
             "description": d.description, "website": d.website, "status": d.status,
             "created_at": d.created_at.isoformat() if d.created_at else None}
            for d in items
        ],
        "total": count,
    }


@router.post("/developers", status_code=201)
async def register_developer(
    body: dict,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_portal_or_admin),
):
    user_id = auth["user_id"]

    existing = (await db.execute(
        select(store_models.Developer).where(store_models.Developer.user_id == user_id)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "已注册为开发者")

    user = auth["user"]
    dev = store_models.Developer(
        user_id=user_id,
        display_name=body.get("display_name") or getattr(user, "nickname", None) or getattr(user, "username", ""),
        description=body.get("description"),
        website=body.get("website"),
    )
    db.add(dev)
    await db.commit()
    await db.refresh(dev)
    return {"id": dev.id, "display_name": dev.display_name}


# ============================================================
# 公开商店目录（无需鉴权，仅展示已审核通过的最新版）
# ============================================================

CATEGORY_LABELS: dict[str, str] = {
    # 平台通用
    "business": "业务应用",
    "productivity": "效率工具",
    "content": "内容管理",
    "system": "系统扩展",
    "ai": "AI 能力",
    # MES / 工业域
    "production": "生产管理",
    "equipment": "设备管理",
    "quality": "质量管理",
    "warehouse": "仓储物流",
    "purchase": "采购供应",
    "sales": "销售营销",
    "finance": "财务金融",
}
CATEGORY_ORDER = [
    "business", "production", "equipment", "quality", "warehouse",
    "purchase", "sales", "finance", "ai", "productivity", "content", "system",
]

# 允许接收应用提交的产品（= 有可安装宿主的产品线）。product 只负责「归属哪个产品 / 分发隔离」，
# 与门户 cms 的营销产品目录（thinkmes/aisaas/...）解耦；新增产品线须同步此处与前端 products 下拉。
ALLOWED_PRODUCTS = {"cenkor-admin", "cenkormes", "lightmes", "cenkor-process"}
# 应用开发方式（交付安装目标）：
#   platform   平台内置应用（装进 cenkor-admin 自身，包内含 manifest.py + __init__.py）
#   extension  产品扩展插件（交付到对应 MES 实例热挂载，包内含 manifest.json）
#   standalone 独立应用（私有化整包，仅门户展示/售卖，不由平台或实例热挂载）
DEV_METHODS = {"platform", "extension", "standalone"}


def _manifest_dict(value: Any) -> dict[str, Any]:
    """manifest_data 兼容 dict / JSON 字符串两种存储形态。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _stamp(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def _installed_map(db: AsyncSession) -> dict[str, str]:
    """平台已安装应用：{app_key: version}"""
    rows = (
        await db.execute(
            select(InstalledApp.key, InstalledApp.version).where(InstalledApp.status == "installed")
        )
    ).all()
    return {key: version for key, version in rows}


async def _get_intro(db: AsyncSession, product: str, app_key: str):
    """按 (product, app_key) 取应用富介绍旁表记录（可能为 None）。"""
    return (await db.execute(
        select(store_models.AppIntro).where(
            store_models.AppIntro.product == product,
            store_models.AppIntro.app_key == app_key,
        )
    )).scalar_one_or_none()


async def _intros_map(db: AsyncSession, keys):
    """批量取富介绍：{(product, app_key): AppIntro}。按 app_key 一次捞回再本地配对。"""
    app_keys = {k[1] for k in keys}
    if not app_keys:
        return {}
    rows = (await db.execute(
        select(store_models.AppIntro).where(store_models.AppIntro.app_key.in_(app_keys))
    )).scalars().all()
    return {(r.product, r.app_key): r for r in rows}


@router.get("/apps", response_model=dict[str, Any])
async def public_store_apps(
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(None, description="关键词：名称 / 描述 / 作者 / 标签 / 标识"),
    category: str | None = Query(None, description="分类过滤"),
    product: str | None = Query(None, description="目标产品/宿主过滤：cenkormes / lightmes / cenkor-admin ...；留空=全部"),
    sort: str = Query("updated", pattern="^(updated|downloads|name)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100),
):
    """应用商店公开目录：每个 app_key 只取最新的 approved/installed 版本。

    支持关键词搜索、分类筛选、排序与分页；facets 供前端渲染分类计数。
    """
    inner_select = (
        select(
            store_models.AppSubmission.app_key,
            func.max(store_models.AppSubmission.id).label("max_id"),
        )
        .where(store_models.AppSubmission.status.in_(["approved", "installed"]))
    )
    if product:
        inner_select = inner_select.where(store_models.AppSubmission.product == product)
    inner = inner_select.group_by(store_models.AppSubmission.app_key).subquery()
    stmt = (
        select(store_models.AppSubmission, store_models.Developer.display_name)
        .join(store_models.Developer, store_models.AppSubmission.developer_id == store_models.Developer.id)
        .where(store_models.AppSubmission.id.in_(select(inner.c.max_id)))
        .where(store_models.Developer.status == "active")
    )
    rows = (await db.execute(stmt)).all()
    installed = await _installed_map(db)
    # 批量取价格视图（跨源码边界桥）：未装 commerce 时为空 dict ——
    # 商店照常返回，只是不带价格，接口不会因缺定价模块而失败。
    prices = await pricing_bridge.price_map(db, [s.app_key for s, _ in rows])

    intros = await _intros_map(db, [(s.product, s.app_key) for s, _ in rows])
    all_items: list[dict[str, Any]] = []
    for s, author in rows:
        manifest = _manifest_dict(s.manifest_data)
        showcase = SHOWCASE.get(s.app_key, {})
        intro = intros.get((s.product, s.app_key))
        installed_version = installed.get(s.app_key)
        all_items.append({
            "id": s.id,
            "key": s.app_key,
            "app_key": s.app_key,
            "product": s.product,
            "dev_method": s.dev_method or ("platform" if (s.product or "cenkor-admin") == "cenkor-admin" else "extension"),
            "name": s.name,
            "version": s.version,
            "description": s.description or "",
            "summary": (intro.summary if intro else None) or manifest.get("summary") or showcase.get("summary") or (s.description or ""),
            "icon": s.icon,
            "category": s.category,
            "category_label": CATEGORY_LABELS.get(s.category, s.category),
            "author": author,
            "tags": (intro.tags if intro and intro.tags else None) or manifest.get("tags") or showcase.get("tags") or [],
            "download_count": s.download_count,
            "installed": installed_version is not None,
            "installed_version": installed_version,
            "has_update": bool(installed_version and installed_version != s.version),
            "updated_at": _stamp(s.updated_at),
            # None = 免费 / 未定价（前端据此展示「免费」）
            "price": prices.get(s.app_key),
        })

    items = all_items
    keyword = (q or "").strip().lower()
    if keyword:
        def _hit(it: dict[str, Any]) -> bool:
            haystack = " ".join([
                str(it["name"]), str(it["key"]), str(it["description"]),
                str(it["author"]), " ".join(it["tags"]),
            ]).lower()
            return keyword in haystack

        items = [it for it in items if _hit(it)]

    facets_source = items
    if category:
        items = [it for it in items if it["category"] == category]

    if sort == "downloads":
        items = sorted(items, key=lambda it: (-it["download_count"], it["name"]))
    elif sort == "name":
        items = sorted(items, key=lambda it: it["name"])
    else:
        items = sorted(items, key=lambda it: it["updated_at"] or "", reverse=True)

    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start:start + page_size]

    counts: dict[str, int] = {}
    for it in facets_source:
        counts[it["category"]] = counts.get(it["category"], 0) + 1
    ordered = [c for c in CATEGORY_ORDER if c in counts] + [c for c in counts if c not in CATEGORY_ORDER]

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": start + len(page_items) < total,
        "facets": [
            {"key": c, "label": CATEGORY_LABELS.get(c, c), "count": counts[c]}
            for c in ordered
        ],
        "stats": {
            "apps": len(all_items),
            "installed": sum(1 for it in all_items if it["installed"]),
            "upgradable": sum(1 for it in all_items if it["has_update"]),
            "downloads": sum(it["download_count"] for it in all_items),
        },
    }


@router.get("/apps/{app_key}", response_model=dict[str, Any])
async def public_store_app_detail(
    app_key: str,
    db: AsyncSession = Depends(get_db),
):
    """应用详情：最新版本 + 版本历史 + 权限清单 + 平台安装状态。"""
    stmt = (
        select(store_models.AppSubmission, store_models.Developer)
        .join(store_models.Developer, store_models.AppSubmission.developer_id == store_models.Developer.id)
        .where(store_models.AppSubmission.app_key == app_key)
        .where(store_models.AppSubmission.status.in_(["approved", "installed"]))
        .where(store_models.Developer.status == "active")
        .order_by(store_models.AppSubmission.id.desc())
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        raise HTTPException(404, "应用不存在或尚未上架")

    latest, dev = rows[0]
    manifest = _manifest_dict(latest.manifest_data)
    showcase = SHOWCASE.get(app_key, {})
    intro = await _get_intro(db, latest.product, app_key)
    inst = await db.get(InstalledApp, app_key)
    installed_version = inst.version if inst and inst.status == "installed" else None
    # 价格视图（跨源码边界桥）：未装 commerce 时为 {}
    prices = await pricing_bridge.price_map(db, [app_key])

    history = [
        {
            "version": s.version,
            "status": s.status,
            "released_at": _stamp(s.reviewed_at or s.created_at),
            "download_count": s.download_count,
            "is_current": s.id == latest.id,
        }
        for s, _dev in rows
    ]
    # 平台已安装但已不在上架记录里的版本，同样作为历史项展示
    if installed_version and not any(h["version"] == installed_version for h in history):
        history.append({
            "version": installed_version,
            "status": "installed",
            "released_at": None,
            "download_count": 0,
            "is_current": False,
        })

    permissions = manifest.get("permissions_required") or []
    menus = manifest.get("menus") or []

    return {
        "id": latest.id,
        "key": app_key,
        "app_key": app_key,
        "dev_method": latest.dev_method or ("platform" if (latest.product or "cenkor-admin") == "cenkor-admin" else "extension"),
        "name": latest.name,
        "version": latest.version,
        "description": latest.description or "",
        "summary": (intro.summary if intro else None) or manifest.get("summary") or showcase.get("summary") or (latest.description or ""),
        "highlights": (intro.highlights if intro and intro.highlights else None) or manifest.get("highlights") or showcase.get("highlights") or [],
        "tags": (intro.tags if intro and intro.tags else None) or manifest.get("tags") or showcase.get("tags") or [],
        "screenshots": (intro.screenshots if intro and intro.screenshots else None) or manifest.get("screenshots") or showcase.get("screenshots") or [],
        "long_description": (intro.long_description if intro else None),
        "icon": latest.icon,
        "category": latest.category,
        "category_label": CATEGORY_LABELS.get(latest.category, latest.category),
        "download_count": latest.download_count,
        "updated_at": _stamp(latest.updated_at),
        "released_at": _stamp(latest.reviewed_at or latest.created_at),
        "developer": {
            "name": dev.display_name,
            "website": dev.website,
            "description": dev.description,
        },
        "installed": installed_version is not None,
        "installed_version": installed_version,
        "has_update": bool(installed_version and installed_version != latest.version),
        "has_frontend": bool(inst.has_frontend) if inst else False,
        # None = 免费 / 未定价
        "price": prices.get(app_key),
        "permissions": permissions,
        "permission_count": len(permissions),
        "menu_count": len(menus),
        "min_platform_version": manifest.get("min_platform_version"),
        "dependencies": manifest.get("dependencies") or [],
        "versions": history,
        "install_hint": "管理员可在「系统 → 应用管理」中安装或升级该应用",
    }


# ============================================================
# 应用提交
# ============================================================

@router.get("/submissions", response_model=dict[str, Any])
async def list_submissions(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_portal_or_admin),
    status: str | None = None,
    developer_id: int | None = None,
    only_active: bool = Query(False, description="仅返回每个 app_key 当前活跃的那条（installed/approved 各自最新一条）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """查看应用提交列表。管理员看全部，普通开发者只看自己的。"""
    # only_active：每个 app_key 在指定 status 下，只保留最新一条；
    #              且 platform_apps.status 必须为 installed（避免出现"已卸载却还在已安装列表"）。
    if only_active:
        from sqlalchemy import func as sa_func
        from cenkor_admin.apps.system.models import InstalledApp as _IA
        # 1) 找出当前 platform_apps 里 status=installed 的 app_key 集合
        active_keys_rows = (await db.execute(
            select(_IA.key).where(_IA.status == "installed")
        )).scalars().all()
        active_keys = set(active_keys_rows)

        # 2) 找出每个 app_key 的最新（按 id 最大）submission
        inner = (
            select(
                store_models.AppSubmission.app_key,
                sa_func.max(store_models.AppSubmission.id).label("max_id"),
            )
            .group_by(store_models.AppSubmission.app_key)
        )
        if status:
            inner = inner.where(store_models.AppSubmission.status == status)
        if developer_id is not None:
            inner = inner.where(store_models.AppSubmission.developer_id == developer_id)
        inner = inner.subquery()
        active_ids_subq = select(inner.c.max_id)
        all_ids = (await db.execute(active_ids_subq)).scalars().all()

        # 3) 过滤：只保留 app_key 仍处于 installed 状态的
        # 需要再次查询拿到 app_key 然后过滤
        rows_with_key = (await db.execute(
            select(store_models.AppSubmission.id, store_models.AppSubmission.app_key)
            .where(store_models.AppSubmission.id.in_(all_ids))
        )).all()
        only_active_ids = {r[0] for r in rows_with_key if r[1] in active_keys}
    else:
        only_active_ids = None
    stmt = (
        select(store_models.AppSubmission, store_models.Developer.display_name)
        .join(store_models.Developer, store_models.AppSubmission.developer_id == store_models.Developer.id)
        .order_by(store_models.AppSubmission.created_at.desc())
    )

    # 如果是 portal 用户，自动限制只看自己的提交
    if auth["user_type"] == "portal":
        dev = (await db.execute(
            select(store_models.Developer).where(
                store_models.Developer.user_id == auth["user_id"]
            )
        )).scalar_one_or_none()
        if not dev:
            developer_id = -1  # 无开发者身份，返回空
        else:
            developer_id = dev.id

    if status:
        stmt = stmt.where(store_models.AppSubmission.status == status)
    if developer_id is not None:
        stmt = stmt.where(store_models.AppSubmission.developer_id == developer_id)
    if only_active_ids is not None:
        if not only_active_ids:
            return {"items": [], "total": 0}
        stmt = stmt.where(store_models.AppSubmission.id.in_(only_active_ids))

    # 注意：不可用 stmt.whereclause 拼 count —— 无筛选条件时 whereclause 为 None，
    # 会生成 `WHERE NULL` 导致 total 恒为 0。直接用 stmt 的 subquery（同 list_developers）。
    count = (await db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    )).scalar() or 0
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).all()

    return {
        "items": [
            {"id": s.id, "app_key": s.app_key, "name": s.name, "version": s.version,
             "description": s.description, "icon": s.icon, "category": s.category,
             "status": s.status, "review_note": s.review_note, "product": s.product or "cenkor-admin",
             "dev_method": s.dev_method or ("platform" if (s.product or "cenkor-admin") == "cenkor-admin" else "extension"),
             "author": author,
             "download_count": s.download_count,
             "created_at": s.created_at.isoformat() if s.created_at else None,
             "reviewed_at": s.reviewed_at.isoformat() if s.reviewed_at else None}
            for s, author in rows
        ],
        "total": count,
    }


@router.post("/submissions", status_code=201)
async def submit_app(
    file: UploadFile = File(...),
    app_key: str = Form(...),
    name: str = Form(...),
    version: str = Form(...),
    description: str = Form(""),
    category: str = Form("system"),
    product: str = Form("cenkor-admin"),
    dev_method: str = Form("extension"),
    pricing: str = Form(""),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_portal_or_admin),
):
    """开发者上传应用 ZIP 包（可选同时提交定价：原价 / 售价 / 限时促销）"""
    user_id = auth["user_id"]

    # 检查开发者身份
    dev = (await db.execute(
        select(store_models.Developer).where(store_models.Developer.user_id == user_id)
    )).scalar_one_or_none()
    if not dev:
        raise HTTPException(403, "请先注册为开发者")

    # 校验文件
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(400, "请上传 ZIP 文件")

    # 校验 app_key 格式
    import re
    if not re.fullmatch(r"[a-z][a-z0-9\-_]{1,49}", app_key):
        raise HTTPException(400, "app_key 格式错误：小写字母开头，只含小写字母/数字/下划线/连字符，2-50位")

    # 校验 version 格式（参与落盘文件名，必须防 ../ 等路径穿越）
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\.\-_]{0,19}", version):
        raise HTTPException(400, "version 格式错误：字母/数字开头，仅含字母数字与 . - _，最长 20 位")

    # 归一化并校验 product / dev_method（模块级白名单，避免各处硬编码漂移）
    product = (product or "cenkor-admin").strip() or "cenkor-admin"
    dev_method = (dev_method or "").strip()
    if product not in ALLOWED_PRODUCTS:
        raise HTTPException(400, f"未知产品「{product}」，允许值：{sorted(ALLOWED_PRODUCTS)}")
    if dev_method not in DEV_METHODS:
        raise HTTPException(400, f"未知开发方式「{dev_method}」，允许值：{sorted(DEV_METHODS)}")

    # ---- 查重与版本闸门：必须在落盘之前 ----
    # 落盘是 `UPLOAD_DIR/{app_key}-{version}.zip` 直接覆盖写。若先写盘再判重，
    # 同版本重传会先把磁盘包换掉、再抛 409 退出，而这条 (product, app_key, version)
    # 下已 approved 的老行 file_path 正指向这个文件、file_hash 还是旧的 —— 包内容
    # 与指纹就此失真。这两道校验只依赖 Form 参数与库里的行，不碰包体，所以能前置。
    existing = (await db.execute(
        select(store_models.AppSubmission).where(
            store_models.AppSubmission.product == product,
            store_models.AppSubmission.app_key == app_key,
            store_models.AppSubmission.version == version,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"版本 {version} 已存在")

    from cenkor_admin.apps.system.models import InstalledApp as _InstalledApp
    from packaging.version import Version as _Version, InvalidVersion as _InvalidVersion
    try:
        new_v = _Version(version)
    except _InvalidVersion:
        raise HTTPException(400, f"version 格式非法，应为 semver（如 1.0.0）：{version}")
    installed_row = (await db.execute(
        select(_InstalledApp).where(_InstalledApp.key == app_key)
    )).scalar_one_or_none()
    if installed_row and installed_row.status == "installed":
        try:
            current_v = _Version(installed_row.version)
            if new_v <= current_v:
                raise HTTPException(
                    400,
                    f"新版本 {version} 必须严格大于已安装版本 {installed_row.version}",
                )
        except _InvalidVersion:
            pass  # 已安装版本号解析失败时不阻塞新版本

    # 定价（可选）：提交时即可带价，JSON 字符串。规则由公开的 pricing_rules 统一校验，
    # 在落盘之前就拦掉非法组合，避免白传一个几百 MB 的包。
    price_payload: dict[str, Any] | None = None
    if (pricing or "").strip():
        try:
            _parsed = json.loads(pricing)
        except json.JSONDecodeError:
            raise HTTPException(400, "定价参数不是合法 JSON") from None
        try:
            price_payload = pricing_rules.normalize_price_fields(_parsed)
        except pricing_rules.PriceRuleError as exc:
            raise HTTPException(400, f"定价不合法：{exc}") from None

    # 保存文件并校验
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = UPLOAD_DIR / f"{app_key}-{version}.zip"
    content = await file.read(MAX_APP_UPLOAD_BYTES + 1)
    if len(content) > MAX_APP_UPLOAD_BYTES:
        raise HTTPException(413, f"应用包过大（超过 {MAX_APP_UPLOAD_BYTES // 1024 // 1024}MB 上限）")
    zip_path.write_bytes(content)

    file_hash = hashlib.sha256(content).hexdigest()

    # 解压校验 manifest：按 dev_method（交付安装目标）分支
    # - platform   平台内置应用：manifest.py + __init__.py（装进 cenkor-admin 自身）
    # - extension  产品扩展插件：manifest.json（交付到对应 MES 实例热挂载）
    # - standalone 独立应用：私有化整包，仅门户展示/售卖，不做安装向强校验
    manifest_data = None
    manifest_ok = False  # 包体校验全部通过才允许留盘
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            if dev_method == "extension":
                # 产品扩展包：根目录或单层目录下要有 manifest.json
                manifest_name = next(
                    (
                        n for n in names
                        if n == "manifest.json" or (n.endswith("/manifest.json") and n.count("/") == 1)
                    ),
                    None,
                )
                if not manifest_name:
                    raise HTTPException(400, "扩展包缺少 manifest.json")
                try:
                    manifest_data = json.loads(zf.read(manifest_name).decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    raise HTTPException(400, "manifest.json 解析失败") from None
                if not isinstance(manifest_data, dict):
                    raise HTTPException(400, "manifest.json 结构非法（应为对象）")
                if manifest_data.get("key") != app_key:
                    raise HTTPException(400, f"manifest.json 中的 key ({manifest_data.get('key')}) 与提交的 app_key ({app_key}) 不一致")
                if not manifest_data.get("version"):
                    raise HTTPException(400, "manifest.json 缺少 version")
                # 一致性：扩展包 manifest 若声明 product，须与提交产品一致
                _mp = manifest_data.get("product")
                if _mp and _mp != product:
                    raise HTTPException(400, f"manifest.product（{_mp}）与提交产品（{product}）不一致")
            elif dev_method == "platform":
                # 平台内置应用：manifest.py + __init__.py（模块式，装进平台自身）
                if "manifest.py" not in names:
                    raise HTTPException(400, "平台应用包缺少 manifest.py")
                if "__init__.py" not in names:
                    raise HTTPException(400, "平台应用包缺少 __init__.py")

                # 读取并解析 manifest
                manifest_content = zf.read("manifest.py").decode("utf-8")
                manifest_data = _parse_manifest(manifest_content)
                if not manifest_data:
                    raise HTTPException(400, "manifest.py 解析失败")

                # 校验 key 一致性
                if manifest_data.get("key") != app_key:
                    raise HTTPException(400, f"manifest 中的 key ({manifest_data.get('key')}) 与提交的 app_key ({app_key}) 不一致")

                # 校验 router.py import 路径（常见错误：from apps.xxx）
                router_names = [n for n in names if n.endswith("router.py")]
                for rn in router_names:
                    router_content = zf.read(rn).decode("utf-8", errors="ignore")
                    if "from apps." in router_content or "import apps." in router_content:
                        raise HTTPException(
                            400,
                            "router.py 中使用了错误的 import 路径 `apps.*`，"
                            f"请改为 `from cenkor_admin.apps.{app_key} import models` 或 `from . import models`",
                        )
            else:
                # 独立应用（standalone）：私有化整包，仅门户展示/售卖，不做安装向强校验。
                # 宽松要求：包内含 manifest.json 或 README 即可；有 manifest.json 则解析留档。
                _has_readme = any(
                    n.upper().startswith("README") or n.upper().endswith("/README.MD")
                    for n in names
                )
                _mn = next(
                    (
                        n for n in names
                        if n == "manifest.json" or (n.endswith("/manifest.json") and n.count("/") == 1)
                    ),
                    None,
                )
                if not _mn and not _has_readme:
                    raise HTTPException(400, "独立应用包需包含 manifest.json 或 README")
                if _mn:
                    try:
                        _md = json.loads(zf.read(_mn).decode("utf-8"))
                        if isinstance(_md, dict):
                            manifest_data = _md
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        pass
                if not manifest_data:
                    # 仅有 README：留最小占位，避免 standalone 包被后面的建单流程判成空 manifest
                    manifest_data = {"key": app_key, "name": name or app_key, "_standalone": True}
        manifest_ok = True
    except zipfile.BadZipFile:
        raise HTTPException(400, "ZIP 文件损坏")
    finally:
        # 判重已前置到落盘之前，所以这里的失败都是「包不合格」而非「版本撞车」；
        # manifest_data 在 key/version 不符时也已解析成功，只靠 `not manifest_data`
        # 会漏删孤包 —— 用显式标志兜住写盘之后的所有 4xx。
        if not manifest_ok:
            zip_path.unlink(missing_ok=True)

    submission = store_models.AppSubmission(
        developer_id=dev.id,
        product=product,
        dev_method=dev_method,
        app_key=app_key,
        name=name or manifest_data.get("name", app_key),
        version=version,
        description=description or manifest_data.get("description", ""),
        icon=manifest_data.get("icon", "📦"),
        category=category,
        manifest_data=manifest_data,
        file_path=str(zip_path),
        file_hash=file_hash,
        status="pending",
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    # 提交时带的价格：派发事件让收费应用（commerce）落库。
    # 底座部署没装该应用时 events 返回空，定价不落库但提交照常成功。
    pricing_saved = False
    if price_payload is not None:
        try:
            results = await hooks.dispatch(
                "app.submitted",
                app_key=app_key,
                developer_id=dev.id,
                submission_id=submission.id,
                # 定价行的定位键是 (product, app_key)：把这条提交的轴带上，
                # 否则收费侧只能吃列默认值 cenkor-admin，实例按自身轴下单会算成 0 元。
                product=submission.product,
                pricing=price_payload,
            )
            pricing_saved = any(bool(r) for r in results)
        except Exception as _pe:  # noqa: BLE001 - 定价落库失败不影响提交
            log.warning("store.submit_pricing_fail", app_key=app_key, error=str(_pe))

    # 通知所有有审核权限的管理员
    try:
        from cenkor_admin.apps.rbac.models import RolePermission, UserRole, Permission
        from cenkor_admin.apps.notification.models import Notification
        _pid = (await db.execute(
            select(Permission.id).where(Permission.code == "rbac:role:write")
        )).scalar_one_or_none()
        if _pid:
            _role_ids = (await db.execute(
                select(RolePermission.role_id).where(RolePermission.permission_id == _pid)
            )).scalars().all()
            _user_ids = (await db.execute(
                select(UserRole.user_id).where(UserRole.role_id.in_(_role_ids)).distinct()
            )).scalars().all()
            for _uid in _user_ids:
                db.add(Notification(
                    user_id=_uid, type="system",
                    title=f"新应用待审核：{name}",
                    body=f"开发者 {dev.display_name} 提交了「{name}」v{version}，请前往应用商店审核。",
                    link="/system/apps",
                    payload={"submission_id": submission.id, "app_key": app_key},
                ))
            await db.commit()
    except Exception as _ne:
        log.warning("store.submit_notification_fail", error=str(_ne))

    return {
        "id": submission.id,
        "app_key": submission.app_key,
        "status": submission.status,
        "pricing_submitted": price_payload is not None,
        "pricing_saved": pricing_saved,
    }


@router.post("/submissions/batch-review")
async def batch_review_submissions(
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """管理员批量审核应用：一次通过 / 驳回多条待审核提交。

    body: ``{ids: [int], action: 'approve'|'reject', note?: str}``。
    逐条处理，仅对处于 ``pending`` 的提交生效；不存在或非 pending 的记入 ``skipped``
    而不中断其它条目（部分成功语义，返回明细供前端展示进度与跳过原因）。
    """
    ids = body.get("ids") or []
    action = body.get("action")
    note = body.get("note", "")
    if action not in ("approve", "reject"):
        raise HTTPException(400, "action 必须是 approve 或 reject")
    # 去重 + 只保留整数 id，屏蔽畸形输入
    try:
        unique_ids = sorted({int(i) for i in ids})
    except (TypeError, ValueError):
        raise HTTPException(400, "ids 必须是提交 id 的整数数组") from None
    if not unique_ids:
        raise HTTPException(400, "ids 不能为空")

    rows = (await db.execute(
        select(store_models.AppSubmission).where(store_models.AppSubmission.id.in_(unique_ids))
    )).scalars().all()
    found = {r.id: r for r in rows}

    now = datetime.now(timezone.utc)
    updated: list[int] = []
    skipped: list[dict] = []
    for sid in unique_ids:
        sub = found.get(sid)
        if sub is None:
            skipped.append({"id": sid, "reason": "提交记录不存在"})
            continue
        if sub.status != "pending":
            skipped.append({"id": sid, "reason": f"当前状态为 {sub.status}，非待审核"})
            continue
        sub.status = "approved" if action == "approve" else "rejected"
        sub.review_note = note
        sub.reviewed_by = _.id
        sub.reviewed_at = now
        updated.append(sid)

    await db.commit()
    return {
        "action": action,
        "updated": len(updated),
        "ids": updated,
        "skipped": skipped,
        "skipped_count": len(skipped),
    }


@router.post("/submissions/{submission_id}/review")
async def review_submission(
    submission_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """管理员审核应用"""
    sub = await db.get(store_models.AppSubmission, submission_id)
    if not sub:
        raise HTTPException(404, "提交记录不存在")

    action = body.get("action")  # approve / reject
    note = body.get("note", "")

    if action == "approve":
        sub.status = "approved"
    elif action == "reject":
        sub.status = "rejected"
    else:
        raise HTTPException(400, "action 必须是 approve 或 reject")

    sub.review_note = note
    sub.reviewed_by = _.id
    sub.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": sub.id, "status": sub.status}


@router.delete("/submissions/{submission_id}", status_code=204)
async def withdraw_submission(
    submission_id: int,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_portal_or_admin),
):
    """开发者撤回自己的提交（pending / approved / rejected 状态可撤回；installed 不可撤回）。"""
    sub = await db.get(store_models.AppSubmission, submission_id)
    if not sub:
        raise HTTPException(404, "提交记录不存在")

    # 权限检查：管理员可撤回任何；portal 只能撤回自己的
    if auth["user_type"] == "portal":
        dev = (await db.execute(
            select(store_models.Developer).where(
                store_models.Developer.user_id == auth["user_id"]
            )
        )).scalar_one_or_none()
        if not dev or dev.id != sub.developer_id:
            raise HTTPException(403, "无权操作此提交")

    if sub.status == "installed":
        raise HTTPException(400, "已安装的应用无法撤回，请联系管理员卸载")

    # 清理 ZIP 文件
    if sub.file_path and os.path.exists(sub.file_path):
        try:
            os.remove(sub.file_path)
        except Exception:
            pass

    await db.delete(sub)
    await db.commit()
    return None


@router.post("/submissions/{submission_id}/install")
async def install_submission(
    submission_id: int,
    db: AsyncSession = Depends(get_db),
    _: auth_models.User = Depends(require_permission("rbac:role:write")),
):
    """安装已审核通过（或曾安装过）的应用。

    ``approved`` = 首次安装；``installed`` = 重装（应用被卸载后再次安装）。
    必须与 ``public_store_apps`` 的取数条件 ``status in ("approved", "installed")``
    保持一致 —— 否则商店里显示「可安装」的条目点下去会被这里 400 拒绝。
    """
    sub = await db.get(store_models.AppSubmission, submission_id)
    if not sub or sub.status not in ("approved", "installed"):
        raise HTTPException(400, "应用未审核通过")

    # 检查 ZIP 文件存在
    if not sub.file_path or not os.path.exists(sub.file_path):
        raise HTTPException(400, "ZIP 文件不存在，请重新上传")

    # 解压到 apps 目录（兼容 ZIP 根目录或单层子目录打包）
    _guard_against_shadowed_source(sub.app_key)
    app_dir = APPS_DIR / sub.app_key
    try:
        with zipfile.ZipFile(sub.file_path, "r") as zf:
            _extract_app_zip(zf, app_dir)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"解压失败: {e}")

    # 处理前端资源：复制 frontend/dist/ → static/apps/{key}/
    has_frontend = False
    frontend_src = app_dir / "frontend" / "dist"
    if frontend_src.exists():
        target_dir = FRONTEND_STATIC_DIR / sub.app_key
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(frontend_src, target_dir)
        has_frontend = True
        log.info("store.frontend_copied", key=sub.app_key, target=str(target_dir))

    # 处理数据库迁移文件：拷贝 ZIP 中的 alembic/versions/*.py
    _copy_migration_files(app_dir, sub.app_key)

    # 立即执行数据库迁移（安装时建表，无需重启）
    try:
        from alembic.config import Config
        from alembic import command
        _alembic_cfg = Config(
            str(Path(__file__).resolve().parent.parent.parent.parent.parent / "alembic.ini")
        )
        command.upgrade(_alembic_cfg, "head")
        log.info("store.migration_upgrade_ok", app_key=sub.app_key)
    except Exception as e:
        log.warning("store.migration_upgrade_fail", app_key=sub.app_key, error=str(e))

    # 更新状态
    sub.status = "installed"

    # 自动安装（注册权限/菜单）
    warnings: list[str] = []
    try:
        from cenkor_admin.apps.system.app_registry import install_app
        await install_app(db, sub.app_key)
    except Exception as e:
        log.warning("store.install.auto_failed", app_key=sub.app_key, error=str(e))
        raise HTTPException(500, f"应用注册失败: {e}")

    # 动态注册 API 路由（无需重启后端）
    route_registered = False
    try:
        from cenkor_admin.api.v1 import register_app_router
        route_registered = register_app_router(sub.app_key)
        if not route_registered and (app_dir / "router.py").exists():
            warnings.append("API 路由注册失败，请检查 router.py 中的 import 路径")
    except Exception as e:
        log.warning("store.route_register_failed", app_key=sub.app_key, error=str(e))
        warnings.append(f"API 路由注册异常: {e}")

    # 更新 has_frontend 标记
    installed_row = (await db.execute(
        select(InstalledApp).where(InstalledApp.key == sub.app_key)
    )).scalar_one_or_none()
    if installed_row:
        installed_row.has_frontend = has_frontend

    await db.commit()
    return {
        "ok": True,
        "app_key": sub.app_key,
        "has_frontend": has_frontend,
        "route_registered": route_registered,
        "warnings": warnings,
    }


# ============================================================
# 工具函数
# ============================================================

# alembic 迁移文件目录
ALEMBIC_VERSIONS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "alembic" / "versions"


def _guard_against_shadowed_source(app_key: str) -> None:
    """安装前检查：外置目录已有同名应用源码时拒绝安装。

    ``cenkor_admin.apps`` 的 ``__path__`` 是【内置目录在前、外置目录在后】，
    而商店安装落盘到内置目录 —— 于是一份陈旧的安装副本会从此遮蔽外置那份
    维护中的源码：改外置代码不生效，运行时拿到的是包里的旧 API。
    实例（2026-10-08）：payment 1.0.0 装进内置目录后，外置 payment 已有的
    ``detect_terminal`` 终端选路在 commerce 下单时报 AttributeError。

    只拦「外置有源码 + 要装到内置」这一种重叠；客户实例上没手工维护的外置
    源码，正常安装不受影响。
    """
    external_dir = EXTERNAL_APPS_DIR / app_key
    if not external_dir.is_dir():
        return
    raise HTTPException(
        409,
        f"「{app_key}」的源码在外置目录 backend/src/apps/{app_key}/，"
        f"而商店安装会写到内置目录 backend/src/cenkor_admin/apps/{app_key}/；"
        "内置副本优先级更高，装完会遮蔽外置源码（改了不生效、运行时拿到旧 API）。"
        "请先把外置目录改名或移除，或直接更新外置源码后重装。",
    )


def _extract_app_zip(zf: zipfile.ZipFile, app_dir: Path) -> None:
    """解压 App ZIP，自动剥离单层根目录（如 my_todo/manifest.py）。

    安全约束（防路径穿越 / zip bomb）：
    - 拒绝绝对路径、盘符、`..` 等可能越出 app_dir 的条目；
    - 条目数、单文件解压大小、解压总大小均设上限；
    - 先完成全部校验，再删除旧目录并落盘，避免半途失败留下脏状态。
    """
    names = [n for n in zf.namelist() if n and not n.endswith("/")]
    if not names:
        raise HTTPException(400, "ZIP 包为空")
    if len(names) > MAX_ZIP_ENTRIES:
        raise HTTPException(400, f"ZIP 内文件条目过多（超过 {MAX_ZIP_ENTRIES}）")

    if "manifest.py" in names:
        prefix = ""
    else:
        manifest_paths = [n for n in names if n.endswith("manifest.py")]
        if not manifest_paths:
            raise HTTPException(400, "ZIP 包缺少 manifest.py")
        manifest_path = min(manifest_paths, key=len)
        prefix = manifest_path[: -len("manifest.py")]

    app_dir_resolved = app_dir.resolve()
    entries: list[tuple[str, str, Path]] = []
    total_size = 0
    for name in names:
        if prefix and not name.startswith(prefix):
            continue
        rel = name[len(prefix):] if prefix else name
        if not rel:
            continue
        rel_norm = rel.replace("\\", "/")
        parts = rel_norm.split("/")
        if rel_norm.startswith("/") or ":" in parts[0] or ".." in parts:
            raise HTTPException(400, f"ZIP 含非法路径条目: {rel}")
        target = (app_dir / rel).resolve()
        if app_dir_resolved not in target.parents:
            raise HTTPException(400, f"ZIP 含越界路径条目: {rel}")
        info = zf.getinfo(name)
        if info.is_dir():
            continue
        if info.file_size > MAX_ZIP_FILE_SIZE:
            raise HTTPException(400, f"ZIP 内单文件解压后过大: {rel}")
        total_size += info.file_size
        entries.append((name, rel, target))

    if total_size > MAX_ZIP_TOTAL_SIZE:
        raise HTTPException(400, "ZIP 解压总大小超限（疑似 zip bomb）")

    if app_dir.exists():
        shutil.rmtree(app_dir)
    app_dir.mkdir(parents=True)

    for name, rel, target in entries:
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(name) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)


def _migration_revision_exists(revision_id: str) -> bool:
    """检查 revision ID 是否已存在于平台迁移目录。"""
    import re
    pattern = re.compile(
        rf"""revision(?:\s*:\s*str)?\s*=\s*['\"]{re.escape(revision_id)}['\"]"""
    )
    for f in ALEMBIC_VERSIONS_DIR.glob("*.py"):
        try:
            if pattern.search(f.read_text(encoding="utf-8")):
                return True
        except OSError:
            continue
    return False


def _read_migration_revision(path: Path) -> str | None:
    import re
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"""revision(?:\s*:\s*str)?\s*=\s*['\"]([^'\"]+)['\"]""", content)
    return m.group(1) if m else None


def _copy_migration_files(app_dir: Path, app_key: str) -> None:
    """将 ZIP 中 alembic/versions/*.py 拷贝到平台的迁移目录（跳过已存在的 revision）。"""
    migration_src = app_dir / "alembic" / "versions"
    if not migration_src.exists():
        return
    for f in sorted(migration_src.iterdir()):
        if f.suffix != ".py" or f.name.startswith("_"):
            continue
        revision_id = _read_migration_revision(f)
        if revision_id and _migration_revision_exists(revision_id):
            log.info("store.migration_skipped", revision=revision_id, app_key=app_key)
            continue
        dst = ALEMBIC_VERSIONS_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{app_key}_{f.name}"
        shutil.copy2(f, dst)
        log.info("store.migration_copied", src=f.name, dst=dst.name)


def _parse_manifest(content: str) -> dict | None:
    """安全解析 manifest.py 内容"""
    try:
        # 提取 MANIFEST 关键字段（正则提取，不执行代码）
        import re
        result = {}

        # 提取 key
        m = re.search(r'key\s*=\s*["\']([^"\']+)["\']', content)
        if m: result["key"] = m.group(1)

        # 提取 name
        m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
        if m: result["name"] = m.group(1)

        # 提取 version
        m = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
        if m: result["version"] = m.group(1)

        # 提取 author
        m = re.search(r'author\s*=\s*["\']([^"\']+)["\']', content)
        if m: result["author"] = m.group(1)

        # 提取 description
        m = re.search(r'description\s*=\s*["\']([^"\']+)["\']', content)
        if m: result["description"] = m.group(1)

        # 提取 icon
        m = re.search(r'icon\s*=\s*["\']([^"\']+)["\']', content)
        if m: result["icon"] = m.group(1)

        # 提取 category
        m = re.search(r'category\s*=\s*["\']([^"\']+)["\']', content)
        if m: result["category"] = m.group(1)

        # 提取 permissions_required 列表
        m = re.search(r'permissions_required\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if m:
            perms = re.findall(r'["\']([^"\']+)["\']', m.group(1))
            result["permissions_required"] = perms

        # 提取 menus（简化提取）
        menus_match = re.search(r'menus\s*=\s*\[(.*?)\]\s*\)', content, re.DOTALL)
        if menus_match:
            result["menus_raw"] = menus_match.group(0)[:500]  # 保留原始内容

        return result if result.get("key") else None
    except Exception:
        return None


# ============================================================
# 通用安装入口（商店安装 / 云端授权安装共用）
# ============================================================

async def install_app_from_zip(
    db: AsyncSession, app_key: str, zip_path: Path
) -> dict[str, Any]:
    """从 ZIP 安装应用到 apps/ 目录。

    与 `install_submission` 的处理步骤一致（解压 → 前端资源 → 迁移文件 →
    alembic upgrade → install_app 注册 → 动态路由），差别只在于包来源：
    商店安装取自 submission.file_path，云端授权安装取自本地临时副本。

    返回 {has_frontend, route_registered, warnings}。
    """
    if not zip_path.exists():
        raise HTTPException(400, "ZIP 文件不存在")

    _guard_against_shadowed_source(app_key)
    app_dir = APPS_DIR / app_key
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            _extract_app_zip(zf, app_dir)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"解压失败: {e}") from e

    # 前端资源：frontend/dist → static/apps/{key}/
    has_frontend = False
    frontend_src = app_dir / "frontend" / "dist"
    if frontend_src.exists():
        target_dir = FRONTEND_STATIC_DIR / app_key
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(frontend_src, target_dir)
        has_frontend = True

    # 数据库迁移文件
    _copy_migration_files(app_dir, app_key)
    try:
        from alembic import command
        from alembic.config import Config

        _alembic_cfg = Config(
            str(Path(__file__).resolve().parent.parent.parent.parent.parent / "alembic.ini")
        )
        command.upgrade(_alembic_cfg, "head")
    except Exception as e:  # noqa: BLE001
        log.warning("store.migration_upgrade_fail", app_key=app_key, error=str(e))

    warnings: list[str] = []
    try:
        from cenkor_admin.apps.system.app_registry import install_app

        await install_app(db, app_key)
    except Exception as e:  # noqa: BLE001
        log.warning("store.install.auto_failed", app_key=app_key, error=str(e))
        raise HTTPException(500, f"应用注册失败: {e}") from e

    route_registered = False
    try:
        from cenkor_admin.api.v1 import register_app_router

        route_registered = register_app_router(app_key)
        if not route_registered and (app_dir / "router.py").exists():
            warnings.append("API 路由注册失败，请检查 router.py 中的 import 路径")
    except Exception as e:  # noqa: BLE001
        log.warning("store.route_register_failed", app_key=app_key, error=str(e))
        warnings.append(f"API 路由注册异常: {e}")

    installed_row = (await db.execute(
        select(InstalledApp).where(InstalledApp.key == app_key)
    )).scalar_one_or_none()
    if installed_row:
        installed_row.has_frontend = has_frontend

    await db.commit()
    log.info("store.installed_from_zip", app_key=app_key, has_frontend=has_frontend)
    return {
        "has_frontend": has_frontend,
        "route_registered": route_registered,
        "warnings": warnings,
    }

# ============================================================
# 应用富介绍（开发者后台编辑 / 门户详情读取）
# ============================================================

_INTRO_MAX_HTML = 200_000
_INTRO_MAX_UPLOAD = 8 * 1024 * 1024


def _clean_str_list(value, limit=50):
    """把用户传入的字符串数组清洗为去空、限长列表；非 list 视为未提供。"""
    if not isinstance(value, list):
        return None
    out = []
    for x in value:
        item = str(x).strip()
        if item:
            out.append(item[:500])
        if len(out) >= limit:
            break
    return out


def _clean_long_html(value):
    """富文本 HTML 纵深防御：体积上限 + 剥离 script/iframe/on* /javascript:。

    真正的 XSS 边界在渲染端（门户用 DOMPurify 净化后再 v-html）；这里的剥离只是避免
    库内长期存着明显的可执行片段。
    """
    if value is None:
        return None
    import re as _re
    s = str(value)
    if len(s) > _INTRO_MAX_HTML:
        s = s[:_INTRO_MAX_HTML]
    s = _re.sub(r'(?is)<\\s*script.*?<\\s*/\\s*script\\s*>', '', s)
    s = _re.sub(r'(?is)<\\s*iframe.*?<\\s*/\\s*iframe\\s*>', '', s)
    s = _re.sub(r'(?is)\\son[a-z]+\\s*=\\s*\"[^\"]*\"', '', s)
    s = _re.sub("(?is)"+chr(34)+"\\son[a-z]+\\s*=\\s*"+chr(39)+"[^"+chr(39)+"]*"+chr(39)+chr(34), "", s)
    s = _re.sub(r'(?is)\\son[a-z]+\\s*=\\s*[^\\s>]+', '', s)
    s = _re.sub(r'(?is)javascript:', '', s)
    return s


async def _assert_intro_access(db: AsyncSession, auth: dict, product: str, app_key: str) -> None:
    """管理员可编辑任意应用介绍；portal 开发者只能编辑自己提交过的 (product, app_key)。"""
    if auth["user_type"] == "admin":
        return
    dev = (await db.execute(
        select(store_models.Developer).where(store_models.Developer.user_id == auth["user_id"])
    )).scalar_one_or_none()
    if not dev:
        raise HTTPException(403, "请先注册为开发者")
    has = (await db.execute(
        select(store_models.AppSubmission.id).where(
            store_models.AppSubmission.developer_id == dev.id,
            store_models.AppSubmission.product == product,
            store_models.AppSubmission.app_key == app_key,
        ).limit(1)
    )).scalar_one_or_none()
    if not has:
        raise HTTPException(403, "无权编辑该应用的介绍")


@router.get("/intro/{app_key}", response_model=dict[str, Any])
async def get_app_intro(
    app_key: str,
    product: str = Query("cenkor-admin"),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_portal_or_admin),
):
    """读取某应用当前富介绍（供开发者后台编辑器回填）。"""
    await _assert_intro_access(db, auth, product, app_key)
    intro = await _get_intro(db, product, app_key)
    return {
        "product": product,
        "app_key": app_key,
        "summary": (intro.summary if intro else None) or "",
        "highlights": (intro.highlights if intro and intro.highlights else []) or [],
        "tags": (intro.tags if intro and intro.tags else []) or [],
        "screenshots": (intro.screenshots if intro and intro.screenshots else []) or [],
        "long_description": (intro.long_description if intro else None) or "",
        "updated_at": _stamp(intro.updated_at) if intro else None,
    }


@router.put("/intro/{app_key}", response_model=dict[str, Any])
async def put_app_intro(
    app_key: str,
    body: dict,
    product: str = Query("cenkor-admin"),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_portal_or_admin),
):
    """创建/更新某应用富介绍（按 (product, app_key) upsert）。"""
    await _assert_intro_access(db, auth, product, app_key)
    summary = (str(body.get("summary") or "").strip()[:500] or None)
    highlights = _clean_str_list(body.get("highlights")) or []
    tags = _clean_str_list(body.get("tags"), 10) or []
    screenshots = _clean_str_list(body.get("screenshots")) or []
    long_description = _clean_long_html(body.get("long_description"))

    intro = await _get_intro(db, product, app_key)
    if not intro:
        intro = store_models.AppIntro(product=product, app_key=app_key)
        db.add(intro)
    intro.summary = summary
    intro.highlights = highlights
    intro.tags = tags
    intro.screenshots = screenshots
    intro.long_description = long_description
    intro.updated_by = auth["user_id"]
    await db.commit()
    return {"ok": True, "product": product, "app_key": app_key}


@router.post("/media/upload", response_model=dict[str, Any])
async def store_media_upload(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_portal_or_admin),
):
    """富介绍配图上传。

    cms 的 /media/upload 需要 admin token，开发者（portal token）用不了；这里给商店域
    单独开一条接受 portal/admin token 的图片上传通道，复用统一 s3 driver。
    """
    if not file.filename:
        raise HTTPException(400, "缺少文件")
    content = await file.read()
    if not content:
        raise HTTPException(400, "空文件")
    if len(content) > _INTRO_MAX_UPLOAD:
        raise HTTPException(413, "图片过大（超过 8MB 上限）")
    ctype = file.content_type or "application/octet-stream"
    if not ctype.startswith("image/"):
        raise HTTPException(400, "仅支持图片文件")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "png"
    if ext not in {"png", "jpg", "jpeg", "gif", "webp"}:
        ext = "png"
    key = "app-intro/" + uuid.uuid4().hex + "." + ext
    bucket = await s3.public_bucket()
    await s3.ensure_bucket(bucket)
    await s3.upload_fileobj(bucket, key, io.BytesIO(content), ctype)
    url = await s3.public_url(bucket, key)
    log.info("store.intro_media_uploaded", key=key, user_type=auth["user_type"])
    return {"url": url, "key": key, "bucket": bucket}


# ============================================================
# 应用市场（官方目录浏览 / 授权码一键安装）
# 开源层实现；商业版的 commerce / cloud_router 是另一条带库表的链路。
# 放在文件末尾 include，避免与 market_router 内部的延迟导入形成环。
# ============================================================
from cenkor_admin.apps.system.market_router import router as market_router  # noqa: E402

router.include_router(market_router, prefix="/official", tags=["app-official"])
