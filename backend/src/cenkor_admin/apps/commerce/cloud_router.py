"""应用市场云端绑定：客户实例 ↔ 官方账号 的凭证握手 + 官方目录 / 已购

挂在 `/api/v1/store` 下（与 store_router / commerce_router 共用前缀）。
同一份代码在两种部署里跑，角色由 `CENKOR_CLOUD_URL` 决定：

**授权中心（hub，`CENKOR_CLOUD_URL` 留空）**
- ``POST /public/cloud/device/start``      实例申请一次性绑定码（免鉴权）
- ``POST /public/cloud/device/poll``       实例轮询换取长期实例令牌（免鉴权）
- ``GET  /public/cloud/device/preview``    门户确认前预览（portal token）
- ``POST /public/cloud/device/approve``    门户确认 / 拒绝绑定（portal token）
- ``GET  /cloud/my-purchases``             实例令牌：本账号已购（供客户实例拉取）
- ``POST /cloud/instance/revoke-self``     实例令牌：实例自解绑
- ``GET  /account/purchases``              门户：我的已购
- ``GET  /account/instances``              门户：我绑定的实例
- ``POST /account/instances/{uid}/revoke`` 门户：吊销某实例

**客户实例（spoke，`CENKOR_CLOUD_URL` 指向你的云）**
- ``POST /cloud/bind/start``   申请绑定码
- ``POST /cloud/bind/poll``    轮询并落地实例凭证
- ``GET  /cloud/status``       绑定状态（含门户确认链接）
- ``POST /cloud/unbind``       解绑（本地清凭证 + 尽力通知云端吊销）
- ``GET  /cloud/catalog``      官方应用市场目录（转发官方云公开目录 + 本地已装状态）
- ``GET  /cloud/purchases``    已购列表（带实例令牌转发）

**安全设计**：刻意不学 FastAdmin 把官网账号 token 存进客户实例。
实例拿到的是一次性绑定码换来的**长期实例令牌**（随机 48 字节，云端只存 sha256），
可在门户随时吊销；实例侧不持有任何门户账号凭证。
"""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import require_permission
from cenkor_admin.apps.commerce import models as cm
from cenkor_admin.apps.commerce import pricing
from cenkor_admin.apps.portal import models as portal_models
from cenkor_admin.apps.system import store_models
from cenkor_admin.apps.system.models import InstalledApp
from cenkor_admin.apps.system.store_router import require_portal_or_admin, security
from cenkor_admin.apps.system.versioning import ver_tuple
from cenkor_admin.core import licensing
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.db import get_db

log = structlog.get_logger()
router = APIRouter()

DEVICE_TTL_SECONDS = 600                              # 绑定码有效期 10 分钟
POLL_INTERVAL = 3                                     # 建议轮询间隔（秒）
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"    # 去掉 0/O/1/I，便于口述
DEFAULT_PORTAL_URL = "https://portal.cenkor.cn"


# ============================================================
# 工具
# ============================================================

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def _cloud_base() -> str:
    """官方云地址；空字符串代表本机就是授权中心。"""
    return (get_settings().CENKOR_CLOUD_URL or "").rstrip("/")


def _portal_base() -> str:
    return (get_settings().PORTAL_PUBLIC_URL or DEFAULT_PORTAL_URL).rstrip("/")


def _hub_guard() -> None:
    """只在授权中心实例可用 —— 否则会把客户实例也变成可签发实例令牌的节点。"""
    if _cloud_base():
        raise HTTPException(409, "本实例是客户端实例，该接口只在授权中心提供")


def _spoke_guard() -> str:
    """只在客户实例可用，返回官方云地址。"""
    cloud = _cloud_base()
    if not cloud:
        raise HTTPException(409, "本实例是授权中心，无需绑定官方账号")
    return cloud


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _gen_user_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


async def _unique_user_code(db: AsyncSession) -> str:
    """生成未被占用的 user_code（32^8 空间，碰撞概率可忽略，仍做一次兜底检查）。"""
    for _ in range(8):
        code = _gen_user_code()
        hit = (await db.execute(
            select(cm.CloudDeviceCode.id).where(cm.CloudDeviceCode.user_code == code)
        )).first()
        if not hit:
            return code
    raise HTTPException(500, "生成绑定码失败，请重试")


async def _client_row(db: AsyncSession) -> cm.CloudClient | None:
    return (await db.execute(select(cm.CloudClient).order_by(cm.CloudClient.id))).scalars().first()


async def require_instance_token(
    creds=Depends(security),
    db: AsyncSession = Depends(get_db),
) -> cm.CloudInstance:
    """实例令牌鉴权（客户实例 → 官方云）。

    Raises:
        HTTPException: 401 未带令牌 / 令牌无效 / 已吊销。
    """
    if not creds or not creds.credentials:
        raise HTTPException(401, "未提供实例令牌")
    inst = (await db.execute(
        select(cm.CloudInstance).where(
            cm.CloudInstance.token_hash == _hash_token(creds.credentials),
            cm.CloudInstance.revoked_at.is_(None),
        )
    )).scalars().first()
    if not inst:
        raise HTTPException(401, "实例令牌无效或已吊销")

    # 心跳：刷新最后活跃时间。
    # commit 会让 ORM 属性过期，必须 refresh 再交给路由序列化 —— 否则异步上下文
    # 里同步访问过期属性会抛 MissingGreenlet。
    inst.last_seen_at = _now()
    await db.commit()
    await db.refresh(inst)
    return inst


# ============================================================
# 已购列表（门户 / 实例共用同一份查询）
# ============================================================

async def _price_map_safe(db: AsyncSession, keys: list[str]) -> dict[str, dict[str, Any]]:
    """取买家可见价格；定价模块异常不应拖垮「我的已购」。"""
    if not keys:
        return {}
    try:
        return await pricing.public_price_map(db, keys)
    except Exception as exc:  # noqa: BLE001
        log.warning("cloud.price_map_failed", error=str(exc))
        return {}


async def _latest_version_map(db: AsyncSession, keys: list[str]) -> dict[tuple[str, str | None], str]:
    """每个 app_key 的「最新可分发版本」，供实例侧算「可更新 N 个」。

    选取口径与 `commerce_router._fetch_package` 完全一致：**同状态下版本号最大**的那条
    （不是 id 最大 —— 先上 2.0 再补 1.9 修现场时，按 id 会长期把「最新」停在旧版本号上，
    与商店目录对外声明的 latest 对不上号）。并列时取 id 大的。

    只有这一条最新行真的取不到包（file_path 缺失/文件不在盘上）才跳过该 app_key ——
    注意是「跳过这个 app」而不是「退而展示更旧的版本」：那样会催用户去装一个
    _fetch_package 必然 409 的更新提示。
    同时给出 product=None 的兜底键，兼容不认产品轴的旧实例与旧授权。
    定位失败不影响「我的已购」本体，返回空表（与 _price_map_safe 同一取向）。
    """
    if not keys:
        return {}
    try:
        rows = (await db.execute(
            select(
                store_models.AppSubmission.app_key,
                store_models.AppSubmission.product,
                store_models.AppSubmission.version,
                store_models.AppSubmission.file_path,
                store_models.AppSubmission.id,
            )
            .where(
                store_models.AppSubmission.app_key.in_(keys),
                store_models.AppSubmission.status.in_(("approved", "published", "installed")),
                # 撤回上架的版本不再「可更新」：yank 只阻止新下载，已装实例照常跑。
                store_models.AppSubmission.yanked_at.is_(None),
            )
        )).all()
    except Exception as exc:  # noqa: BLE001
        log.warning("cloud.latest_version_failed", error=str(exc))
        return {}
    rows = sorted(rows, key=lambda r: (ver_tuple(r[2]), r[4] or 0), reverse=True)
    out: dict[tuple[str, str | None], str] = {}
    decided: set[tuple[str, str | None]] = set()
    for app_key, product, version, file_path, _id in rows:
        for pair in ((app_key, product or None), (app_key, None)):
            if pair in decided:
                continue
            # 每个键只由「版本号最大的那条」决定：有包就报版本，没包就不报，绝不回退到旧版本。
            decided.add(pair)
            if file_path and os.path.exists(file_path):
                out[pair] = str(version or "")
    return out


async def _purchases_for(db: AsyncSession, portal_user_id: int, product: str | None = None) -> list[dict[str, Any]]:
    """某门户账号的已购列表（授权 + 价格 + 已绑实例数）。传入 product 则只返回该产品的已购。"""
    stmt = (
        select(cm.AppLicense)
        .where(
            cm.AppLicense.buyer_type == "portal",
            cm.AppLicense.buyer_id == portal_user_id,
        )
    )
    if product:
        stmt = stmt.where(cm.AppLicense.product == product)
    lics = (await db.execute(stmt.order_by(cm.AppLicense.id.desc()))).scalars().all()
    if not lics:
        return []

    keys = sorted({l.app_key for l in lics})
    prices = await _price_map_safe(db, keys)
    versions = await _latest_version_map(db, keys)

    # 每个授权已激活的实例数（一次聚合查询搞定，避免 N+1）
    lic_ids = [l.id for l in lics]
    bind_rows = (await db.execute(
        select(cm.AppLicenseBinding.license_id, func.count())
        .where(
            cm.AppLicenseBinding.license_id.in_(lic_ids),
            cm.AppLicenseBinding.revoked_at.is_(None),
        )
        .group_by(cm.AppLicenseBinding.license_id)
    )).all()
    bind_counts = {int(r[0]): int(r[1]) for r in bind_rows}

    out: list[dict[str, Any]] = []
    for l in lics:
        out.append({
            "license_key": l.license_key,
            "app_key": l.app_key,
            "app_name": l.app_name,
            "model": l.model,
            "seats": l.seats,
            "status": l.status,
            "order_id": l.order_id,
            "issued_at": _iso(l.issued_at),
            "activated_at": _iso(l.activated_at),
            "expires_at": _iso(l.expires_at),          # None = 永久（一次性买断）
            "permanent": l.expires_at is None,
            "bound_instances": bind_counts.get(l.id, 0),
            "max_instances": l.max_instances,
            "bound_domain": l.bound_domain,
            "price": prices.get(l.app_key),
            # 产品轴：实例侧据此拒绝把 A 产品的授权装进 B 产品实例（跨产品误装的最后一道闸）。
            # 纯增量字段，门户「我的已购」与 hub 自身消费方不受影响。
            "product": l.product,
            # 最新可分发版本：实例侧 `/market/status` 据此算「可更新 N 个」。
            # 空串 = 未知（老 hub、或该 app_key 没有已审核且文件在位的发布行），
            # 实例侧对空值一律不计入可更新，绝不拿空值当「有新版」。
            "latest_version": (
                versions.get((l.app_key, l.product or None))
                or versions.get((l.app_key, None), "")
            ),
        })
    return out


def _instance_view(inst: cm.CloudInstance) -> dict[str, Any]:
    return {
        "instance_uid": inst.instance_uid,
        "name": inst.name,
        "instance_url": inst.instance_url,
        "created_at": _iso(inst.created_at),
        "last_seen_at": _iso(inst.last_seen_at),
        "revoked": inst.revoked_at is not None,
    }


# ============================================================
# 授权中心侧：设备码流程
# ============================================================

@router.post("/public/cloud/device/start", response_model=dict[str, Any])
async def device_start(
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
):
    """实例申请一次性绑定码。免鉴权 —— 绑定码本身不携带任何权限。"""
    _hub_guard()

    name = str(body.get("instance_name") or "").strip()[:120] or "未命名实例"
    url = str(body.get("instance_url") or "").strip()[:255]
    uid = str(body.get("instance_uid") or "").strip()[:64]
    product = str(body.get("product") or "cenkor-admin").strip()[:32] or "cenkor-admin"

    row = cm.CloudDeviceCode(
        device_code=secrets.token_urlsafe(32),
        user_code=await _unique_user_code(db),
        status="pending",
        instance_name=name,
        instance_url=url or None,
        instance_uid=uid or None,
        product=product,
        expires_at=_now() + timedelta(seconds=DEVICE_TTL_SECONDS),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    portal = _portal_base()
    return {
        "device_code": row.device_code,
        "user_code": row.user_code,
        "verification_uri": f"{portal}/connect",
        "verification_uri_complete": f"{portal}/connect?code={row.user_code}",
        "expires_in": DEVICE_TTL_SECONDS,
        "interval": POLL_INTERVAL,
    }


@router.post("/public/cloud/device/poll", response_model=dict[str, Any])
async def device_poll(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """实例轮询绑定结果。首次拿到 approved 时换发实例令牌（之后不许再取）。"""
    _hub_guard()

    device_code = str(body.get("device_code") or "").strip()
    if not device_code:
        raise HTTPException(400, "device_code 必填")

    row = (await db.execute(
        select(cm.CloudDeviceCode).where(cm.CloudDeviceCode.device_code == device_code)
    )).scalars().first()
    if not row:
        raise HTTPException(404, "绑定码不存在")

    now = _now()
    if row.status == "pending":
        if row.expires_at < now:
            row.status = "expired"
            await db.commit()
            return {"status": "expired"}
        return {"status": "pending", "interval": POLL_INTERVAL}
    if row.status in ("denied", "expired", "consumed"):
        return {"status": row.status}
    if row.status != "approved":
        return {"status": row.status}

    # approved → 换发长期实例令牌
    token = secrets.token_urlsafe(48)
    uid = (row.instance_uid or "").strip() or f"inst-{secrets.token_hex(8)}"
    token_hash = _hash_token(token)

    inst = (await db.execute(
        select(cm.CloudInstance).where(cm.CloudInstance.instance_uid == uid)
    )).scalars().first()
    if inst:
        # 同机重绑：复用行、换发令牌、清吊销标记
        inst.portal_user_id = int(row.portal_user_id or 0)
        inst.product = row.product or "cenkor-admin"
        inst.name = row.instance_name
        inst.instance_url = row.instance_url
        inst.token_hash = token_hash
        inst.revoked_at = None
        inst.last_seen_at = now
    else:
        db.add(cm.CloudInstance(
            instance_uid=uid,
            portal_user_id=int(row.portal_user_id or 0),
            product=row.product or "cenkor-admin",
            name=row.instance_name,
            instance_url=row.instance_url,
            token_hash=token_hash,
            last_seen_at=now,
        ))

    row.status = "consumed"
    row.consumed_at = now
    await db.commit()

    account = None
    if row.portal_user_id:
        u = await db.get(portal_models.PortalUser, int(row.portal_user_id))
        if u:
            account = u.email or u.username

    log.info("cloud.instance_bound", uid=uid, portal_user=row.portal_user_id, name=row.instance_name)
    return {
        "status": "approved",
        "instance_token": token,
        "instance_uid": uid,
        "account": account,
    }


@router.get("/public/cloud/device/preview", response_model=dict[str, Any])
async def device_preview(
    user_code: str,
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
):
    """门户在确认前展示「你要把哪台实例绑到自己账号」。"""
    _hub_guard()
    if who.get("user_type") != "portal":
        raise HTTPException(403, "请使用门户账号登录后操作")

    code = (user_code or "").strip().upper()
    row = (await db.execute(
        select(cm.CloudDeviceCode).where(cm.CloudDeviceCode.user_code == code)
    )).scalars().first()
    if not row:
        raise HTTPException(404, "绑定码不存在，请核对后重试")

    expired = row.expires_at < _now()
    return {
        "user_code": row.user_code,
        "instance_name": row.instance_name,
        "instance_url": row.instance_url,
        "product": row.product or "cenkor-admin",
        "status": "expired" if expired and row.status == "pending" else row.status,
        "expires_at": _iso(row.expires_at),
        "usable": row.status == "pending" and not expired,
    }


@router.post("/public/cloud/device/approve", response_model=dict[str, Any])
async def device_approve(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
):
    """门户用户确认 / 拒绝把某台实例绑定到自己账号。"""
    _hub_guard()
    if who.get("user_type") != "portal":
        raise HTTPException(403, "请使用门户账号登录后操作")

    code = str(body.get("user_code") or "").strip().upper()
    action = str(body.get("action") or "approve").strip().lower()
    if not code:
        raise HTTPException(400, "user_code 必填")

    row = (await db.execute(
        select(cm.CloudDeviceCode).where(cm.CloudDeviceCode.user_code == code)
    )).scalars().first()
    if not row:
        raise HTTPException(404, "绑定码不存在，请核对后重试")

    now = _now()
    # 过期一律 410：无论「还是 pending 但已超时」还是「轮询已把它置为 expired」，
    # 对调用方的语义都一样 —— 这个码不能再用了。
    if row.expires_at < now and row.status in ("pending", "expired"):
        if row.status == "pending":
            row.status = "expired"
            await db.commit()
        raise HTTPException(410, "绑定码已过期，请在实例上重新发起绑定")

    if row.status != "pending":
        raise HTTPException(409, f"绑定码当前状态为 {row.status}，不可再操作")

    if action in ("deny", "reject"):
        row.status = "denied"
        await db.commit()
        log.info("cloud.device_denied", user_code=code, portal_user=who["user_id"])
        return {"ok": True, "status": "denied"}

    row.status = "approved"
    row.portal_user_id = int(who["user_id"])
    row.approved_at = now
    await db.commit()

    log.info("cloud.device_approved", user_code=code, portal_user=who["user_id"],
             name=row.instance_name)
    return {
        "ok": True,
        "status": "approved",
        "instance_name": row.instance_name,
        "instance_url": row.instance_url,
    }


# ============================================================
# 授权中心侧：实例令牌接口（给客户实例调用）
# ============================================================

@router.get("/cloud/my-purchases", response_model=dict[str, Any])
async def instance_purchases(
    db: AsyncSession = Depends(get_db),
    inst: cm.CloudInstance = Depends(require_instance_token),
):
    """客户实例凭实例令牌拉取「本账号已购的应用」。"""
    _hub_guard()
    items = await _purchases_for(db, inst.portal_user_id, product=inst.product)
    return {
        "items": items,
        "total": len(items),
        "instance": _instance_view(inst),
    }


@router.post("/cloud/instance/revoke-self", response_model=dict[str, Any])
async def instance_revoke_self(
    db: AsyncSession = Depends(get_db),
    inst: cm.CloudInstance = Depends(require_instance_token),
):
    """客户实例自解绑：令牌立即失效。"""
    _hub_guard()
    inst.revoked_at = _now()
    await db.commit()
    log.info("cloud.instance_self_revoked", uid=inst.instance_uid)
    return {"ok": True, "revoked": True}


# ============================================================
# 授权中心侧：门户账号接口
# ============================================================

async def _portal_uid(who: dict) -> int:
    if who.get("user_type") != "portal":
        raise HTTPException(403, "请使用门户账号登录后操作")
    return int(who["user_id"])


@router.get("/account/purchases", response_model=dict[str, Any])
async def account_purchases(
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
):
    """门户「我的应用」：已购应用 + 授权状态 + 可下载。"""
    _hub_guard()
    uid = await _portal_uid(who)
    items = await _purchases_for(db, uid)
    return {"items": items, "total": len(items)}


@router.get("/account/instances", response_model=dict[str, Any])
async def account_instances(
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
):
    """门户：我绑定过的实例（含已吊销，便于排障）。"""
    _hub_guard()
    uid = await _portal_uid(who)
    rows = (await db.execute(
        select(cm.CloudInstance)
        .where(cm.CloudInstance.portal_user_id == uid)
        .order_by(cm.CloudInstance.id.desc())
    )).scalars().all()
    items = [_instance_view(r) for r in rows]
    return {"items": items, "total": len(items)}


@router.post("/account/instances/{instance_uid}/revoke", response_model=dict[str, Any])
async def account_revoke_instance(
    instance_uid: str,
    db: AsyncSession = Depends(get_db),
    who: dict = Depends(require_portal_or_admin),
):
    """门户：吊销某台实例的凭证（换机 / 设备丢失时用）。"""
    _hub_guard()
    uid = await _portal_uid(who)
    inst = (await db.execute(
        select(cm.CloudInstance).where(cm.CloudInstance.instance_uid == instance_uid)
    )).scalars().first()
    if not inst or inst.portal_user_id != uid:
        raise HTTPException(404, "实例不存在或不属于当前账号")
    if inst.revoked_at is None:
        inst.revoked_at = _now()
        await db.commit()
        log.info("cloud.instance_revoked", uid=instance_uid, by=uid)
    return {"ok": True, "instance_uid": instance_uid, "revoked": True}


# ============================================================
# 客户实例侧：绑定
# ============================================================

@router.get("/cloud/status", response_model=dict[str, Any])
async def spoke_status(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission("rbac:role:write")),
):
    """当前实例的云端绑定状态（hub / spoke 都能调，前端据此决定显示什么）。"""
    cloud = _cloud_base()
    row = await _client_row(db)
    return {
        "role": "spoke" if cloud else "hub",
        "hub": cloud or None,
        "bound": row is not None,
        "account": row.account if row else None,
        "token_bound_at": _iso(row.bound_at) if row else None,
        "instance_uid": licensing.compute_instance_fp(),
        "gateway_url": _portal_base(),
        "connect_url": f"{_portal_base()}/connect",
    }


@router.post("/cloud/bind/start", response_model=dict[str, Any])
async def spoke_bind_start(
    body: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission("rbac:role:write")),
):
    """客户实例：向官方云申请一次性绑定码。"""
    cloud = _spoke_guard()
    s = get_settings()

    import socket

    import httpx

    name = str(body.get("instance_name") or "").strip()[:120]
    if not name:
        name = f"{socket.gethostname()} · cenkor-admin"

    payload = {
        "instance_name": name,
        "instance_url": str(body.get("instance_url") or s.PUBLIC_BASE_URL or "")[:255],
        "instance_uid": licensing.compute_instance_fp(),
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{cloud}/api/v1/store/public/cloud/device/start", json=payload
            )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"官方云不可达：{e}") from e
    if r.status_code != 200:
        raise HTTPException(502, f"申请绑定码失败（HTTP {r.status_code}）：{r.text[:200]}")

    out = r.json()
    out["hub"] = cloud
    log.info("cloud.bind_started", hub=cloud, user=user.id)
    return out


@router.post("/cloud/bind/poll", response_model=dict[str, Any])
async def spoke_bind_poll(
    body: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission("rbac:role:write")),
):
    """客户实例：轮询绑定结果；拿到 approved 即落地实例令牌。"""
    cloud = _spoke_guard()
    device_code = str(body.get("device_code") or "").strip()
    if not device_code:
        raise HTTPException(400, "device_code 必填")

    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{cloud}/api/v1/store/public/cloud/device/poll", json={"device_code": device_code}
            )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"官方云不可达：{e}") from e
    if r.status_code != 200:
        raise HTTPException(502, f"轮询失败（HTTP {r.status_code}）：{r.text[:200]}")

    data = r.json()
    status = data.get("status")
    if status != "approved":
        return {"status": status}

    token = str(data.get("instance_token") or "")
    if not token:
        raise HTTPException(502, "官方云未返回实例令牌")

    # 单行表：先清掉旧凭证再写新的
    await db.execute(delete(cm.CloudClient))
    db.add(cm.CloudClient(
        hub_url=cloud,
        instance_uid=str(data.get("instance_uid") or licensing.compute_instance_fp()),
        token=token,
        account=data.get("account"),
        last_poll_at=_now(),
    ))
    await db.commit()

    log.info("cloud.bind_completed", hub=cloud, account=data.get("account"), user=user.id)
    return {
        "status": "approved",
        "account": data.get("account"),
        "instance_uid": data.get("instance_uid"),
        "hub": cloud,
    }


@router.post("/cloud/unbind", response_model=dict[str, Any])
async def spoke_unbind(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission("rbac:role:write")),
):
    """客户实例：解绑。先尽力通知云端吊销，再清本地凭证。"""
    cloud = _cloud_base()
    row = await _client_row(db)
    if not row:
        return {"ok": True, "bound": False}

    if cloud and row.token:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await client.post(
                    f"{cloud}/api/v1/store/cloud/instance/revoke-self",
                    headers={"Authorization": f"Bearer {row.token}"},
                )
        except Exception as exc:  # noqa: BLE001 - 云端不可达也要允许本地解绑
            log.warning("cloud.unbind_notify_failed", error=str(exc))

    await db.execute(delete(cm.CloudClient))
    await db.commit()
    log.info("cloud.unbound", hub=cloud, user=user.id)
    return {"ok": True, "bound": False}


# ============================================================
# 客户实例侧：官方目录 & 已购
# ============================================================

@router.get("/cloud/catalog", response_model=dict[str, Any])
async def spoke_catalog(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission("rbac:role:write")),
):
    """官方应用市场目录：转发官方云公开目录，并合并本地「已安装」状态。

    官方目录是公开数据，未绑定也能浏览；只有「已购 / 安装」需要绑定账号。
    """
    cloud = _spoke_guard()

    import httpx

    # 官方公开目录单页上限 100，按页翻完，避免应用多了只看到第一页
    items: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for page in range(1, 11):
                r = await client.get(
                    f"{cloud}/api/v1/store/apps",
                    params={"page": page, "page_size": 100},
                )
                if r.status_code != 200:
                    raise HTTPException(
                        502, f"官方应用市场返回异常（HTTP {r.status_code}）：{r.text[:200]}"
                    )
                data = r.json()
                batch = data.get("items") or data.get("data") or []
                items.extend(x for x in batch if isinstance(x, dict))
                if len(batch) < 100:
                    break
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"官方应用市场不可达：{e}") from e

    installed: dict[str, str] = {}
    try:
        # platform_apps 的主键列名是 key（不是 app_key）
        rows = (await db.execute(select(InstalledApp))).scalars().all()
        for row in rows:
            if getattr(row, "status", "installed") != "installed":
                continue
            installed[str(row.key)] = str(row.version or "")
    except Exception as exc:  # noqa: BLE001
        log.warning("cloud.installed_map_failed", error=str(exc))

    merged: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        k = str(item.get("key") or item.get("app_key") or "")
        item["app_key"] = k
        item["installed"] = k in installed
        item["installed_version"] = installed.get(k) or None
        item["needs_upgrade"] = bool(
            item["installed"] and item.get("version") and item.get("version") != installed.get(k)
        )
        # 与官方列表字段命名保持一致，前端两处可复用同一套判断
        item["has_update"] = item["needs_upgrade"]
        merged.append(item)

    row = await _client_row(db)
    return {
        "items": merged,
        "total": len(merged),
        "hub": cloud,
        "bound": row is not None,
        "account": row.account if row else None,
    }


@router.get("/cloud/purchases", response_model=dict[str, Any])
async def spoke_purchases(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission("rbac:role:write")),
):
    """客户实例：本账号已购列表（带实例令牌转发官方云）。"""
    cloud = _spoke_guard()
    row = await _client_row(db)
    if not row:
        raise HTTPException(400, "尚未绑定 Cenkor 账号，请先完成绑定")

    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{cloud}/api/v1/store/cloud/my-purchases",
                headers={"Authorization": f"Bearer {row.token}"},
            )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"官方云不可达：{e}") from e

    if r.status_code == 401:
        raise HTTPException(401, "实例令牌已失效，请在「连接 Cenkor 账号」中重新绑定")
    if r.status_code != 200:
        raise HTTPException(502, f"取已购列表失败（HTTP {r.status_code}）：{r.text[:200]}")

    return r.json()
