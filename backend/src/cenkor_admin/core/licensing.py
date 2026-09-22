"""底座侧授权核心（开源部分）

职责边界（重要）：
- **只做验签与状态判断**，不生成授权。签发用的私钥只存在于授权中心（你的云），
  底座内置公钥，因此客户即便拿到全部源码也无法伪造一张有效授权。
- 私钥一旦泄露需轮换，轮换后旧公钥走 ``LICENSE_PUBLIC_KEY_OLD`` 兼容期。

流程：
    （云）下单支付 → 签发 AppLicense + 私钥签名 token
    （客户实例）激活 → 拿到 token 落本地缓存 → 每次启动/定时心跳刷新
    心跳可达 → 用云端返回的新 token
    心跳不可达 → 在 LICENSE_OFFLINE_GRACE_DAYS 内按旧 token 继续放行

本地缓存写在 ``system_settings`` 的 ``license.app.{app_key}``，
缓存被篡改也没用 —— 每次读取都会用内置公钥验签。
"""
from __future__ import annotations

import base64
import hashlib
import importlib
import json
import socket
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Callable

import structlog
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.core.config import get_settings
from cenkor_admin.core.db import get_db

log = structlog.get_logger()

TOKEN_VERSION = 1
SETTING_PREFIX = "license.app."

# 授权中心公钥（Ed25519 raw 32 字节的 base64url）。
# 由 `POST /api/v1/store/licensing/rotate-key` 生成，首次生成后回填到此常量，
# 客户实例即靠它验签。为空时只认本机数据库里的授权（自营部署场景）。
DEFAULT_PUBLIC_KEY_B64: str = "R3zhi7rUPagy-bXgmIqN6i9yLAJrQnQII9TBB8cNBK8"
PUBLIC_KEY_OLD: str = ""


# ============================================================
# 验签（公钥侧；私钥签发逻辑已移至闭源 src/apps/commerce/license_authority.py）
# ============================================================

def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


async def put_setting(db: AsyncSession, key: str, value: str, description: str) -> None:
    """写 system_settings。

    注意：PG 下 `system_settings.value` 实际列类型是 **jsonb**，而 ORM 把它声明成
    String(2000)。直接赋值字符串会报
    `column "value" is of type jsonb but expression is of type character varying`，
    因此这里走原生 SQL 并显式 CAST(:v AS jsonb)。
    """
    if get_settings().is_postgres:
        from sqlalchemy import text

        await db.execute(
            text(
                'INSERT INTO system_settings ("key", "value", description, "group") '
                "VALUES (:k, CAST(:v AS jsonb), :d, 'license') "
                'ON CONFLICT ("key") DO UPDATE '
                'SET "value" = CAST(:v AS jsonb), description = :d'
            ),
            {"k": key, "v": value, "d": description},
        )
    else:
        row = await db.get(auth_models.SystemSetting, key)
        if row:
            row.value = value
            row.description = description
            row.group = "license"
        else:
            db.add(auth_models.SystemSetting(
                key=key, value=value, description=description, group="license"
            ))
    await db.commit()


async def get_setting(db: AsyncSession, key: str) -> str | None:
    """读 system_settings 的字符串值（asyncpg 对 jsonb 默认返回 str）。"""
    row = await db.get(auth_models.SystemSetting, key)
    if not row or row.value is None:
        return None
    value = row.value
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"))


def verify_license_token(token: str, public_key_b64: str | None = None) -> dict[str, Any] | None:
    """验签并返回 payload；签名不合法返回 None。"""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if not token or "." not in token:
        return None
    keys = [public_key_b64 or DEFAULT_PUBLIC_KEY_B64, PUBLIC_KEY_OLD]
    if not keys[0]:
        return None

    try:
        body_b64, sig_b64 = token.split(".", 1)
        body, sig = _b64d(body_b64), _b64d(sig_b64)
    except Exception:
        return None

    for k in keys:
        if not k:
            continue
        try:
            Ed25519PublicKey.from_public_bytes(_b64d(k)).verify(sig, body)
            payload = json.loads(body)
            if payload.get("v") != TOKEN_VERSION:
                return None
            return payload
        except InvalidSignature:
            continue
        except Exception:
            continue
    return None


# ============================================================
# 实例指纹
# ============================================================

@lru_cache(maxsize=1)
def compute_instance_fp() -> str:
    """本机实例指纹。换服务器 / 改 SECRET_KEY 会变，走换绑流程即可。

    只用「数据库地址+库名 / SECRET_KEY / 主机名」参与计算，
    刻意不含数据库密码 —— 改密码不应该导致客户被迫换绑。
    """
    import re

    s = get_settings()
    m = re.search(r"@([^/]+)/([^?]+)", s.DATABASE_URL or "")
    db_ident = m.group(0) if m else (s.DATABASE_URL or "")
    raw = f"{db_ident}|{s.SECRET_KEY}|{socket.gethostname()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ============================================================
# 本地缓存
# ============================================================

async def read_cache(db: AsyncSession, app_key: str) -> dict[str, Any] | None:
    raw = await get_setting(db, SETTING_PREFIX + app_key)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


async def write_cache(db: AsyncSession, app_key: str, data: dict[str, Any]) -> None:
    await put_setting(
        db,
        SETTING_PREFIX + app_key,
        json.dumps(data, separators=(",", ":")),
        f"{app_key} 应用授权状态",
    )


async def clear_cache(db: AsyncSession, app_key: str) -> None:
    row = await db.get(auth_models.SystemSetting, SETTING_PREFIX + app_key)
    if row:
        await db.delete(row)
        await db.commit()


# ============================================================
# 状态
# ============================================================

@dataclass
class LicenseState:
    app_key: str
    required: bool = False
    valid: bool = True
    status: str = "free"          # free/valid/grace/expired/revoked/missing/invalid
    reason: str = ""
    license_key: str | None = None
    expires_at: datetime | None = None
    seats: int = 1
    bound_domain: str | None = None
    offline: bool = False
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_key": self.app_key,
            "required": self.required,
            "valid": self.valid,
            "status": self.status,
            "reason": self.reason,
            "license_key": self.license_key,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "seats": self.seats,
            "bound_domain": self.bound_domain,
            "offline": self.offline,
        }


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


@lru_cache(maxsize=512)
def _manifest_flag(app_key: str) -> bool:
    try:
        mod = importlib.import_module(f"cenkor_admin.apps.{app_key}.manifest")
        m = getattr(mod, "MANIFEST", None)
        return bool(getattr(m, "license_required", False))
    except Exception:
        return False


def is_license_required(app_key: str) -> bool:
    return _manifest_flag(app_key)


async def _refresh_from_cloud(db: AsyncSession, app_key: str, cache: dict[str, Any]) -> dict[str, Any] | None:
    """向授权中心心跳，成功返回新缓存内容。"""
    s = get_settings()
    cloud = (s.CENKOR_CLOUD_URL or "").rstrip("/")
    license_key = cache.get("license_key")
    if not cloud or not license_key:
        return None

    import httpx

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                f"{cloud}/api/v1/store/licenses/heartbeat",
                json={
                    "license_key": license_key,
                    "instance_fp": compute_instance_fp(),
                    "version": s.APP_VERSION,
                },
            )
        if resp.status_code != 200:
            log.warning("licensing.heartbeat_http", app=app_key, code=resp.status_code)
            return None
        data = resp.json()
    except Exception as e:  # noqa: BLE001 - 网络异常一律走离线宽限
        log.warning("licensing.heartbeat_failed", app=app_key, error=str(e))
        return None

    checked_at = datetime.now(timezone.utc).isoformat()
    if not data.get("valid"):
        return {
            "license_key": license_key,
            "token": data.get("token") or cache.get("token"),
            "checked_at": checked_at,
            "cloud_ok": True,
            "invalid_reason": data.get("reason") or "授权已失效",
        }
    return {
        "license_key": license_key,
        "token": data.get("token") or cache.get("token"),
        "checked_at": checked_at,
        "cloud_ok": True,
        "invalid_reason": None,
    }


async def get_license_state(
    db: AsyncSession, app_key: str, *, force_refresh: bool = False
) -> LicenseState:
    """判断某应用在当前实例上的授权状态。"""
    s = get_settings()
    if not is_license_required(app_key):
        return LicenseState(app_key=app_key, required=False, valid=True, status="free")

    state = LicenseState(app_key=app_key, required=True, valid=False)
    cache = await read_cache(db, app_key)
    if not cache:
        state.status = "missing"
        state.reason = "未激活：请在应用商店完成购买后填入授权码"
        return state

    # 心跳刷新（本机即授权中心时不心跳，直接认本地库）
    is_hub = not (s.CENKOR_CLOUD_URL or "").strip()
    due = force_refresh
    if not is_hub and cache.get("checked_at"):
        last = _parse_dt(cache["checked_at"])
        if last and datetime.now(timezone.utc) - last > timedelta(hours=s.LICENSE_HEARTBEAT_HOURS):
            due = True

    if due and not is_hub:
        fresh = await _refresh_from_cloud(db, app_key, cache)
        if fresh:
            cache = fresh
            await write_cache(db, app_key, fresh)

    state.offline = not cache.get("cloud_ok", False)
    state.license_key = cache.get("license_key")

    payload = verify_license_token(cache.get("token") or "")
    if not payload:
        state.status = "invalid"
        state.reason = "授权凭证验签失败（可能被篡改或来自其他授权中心）"
        return state

    state.payload = payload
    state.seats = int(payload.get("seats") or 1)
    state.bound_domain = payload.get("dom")
    state.expires_at = _parse_dt(payload.get("exp"))

    if cache.get("invalid_reason"):
        state.status = "revoked"
        state.reason = str(cache["invalid_reason"])
        return state

    fp = payload.get("fp")
    if fp and fp != compute_instance_fp():
        state.status = "invalid"
        state.reason = "授权与本实例不匹配，请在授权中心换绑"
        return state

    now = datetime.now(timezone.utc)
    if state.expires_at and state.expires_at < now:
        state.status = "expired"
        state.reason = f"授权已于 {state.expires_at.date()} 到期，请续费"
        return state

    # 离线宽限
    if state.offline and cache.get("checked_at"):
        last = _parse_dt(cache["checked_at"])
        if last and now - last > timedelta(days=s.LICENSE_OFFLINE_GRACE_DAYS):
            state.status = "expired"
            state.reason = f"离线超过 {s.LICENSE_OFFLINE_GRACE_DAYS} 天，请恢复网络连接"
            return state
        state.status = "grace"
        state.reason = "授权中心暂时不可达，当前处于离线宽限期"
        state.valid = True
        return state

    state.status = "valid"
    state.valid = True
    state.reason = ""
    return state


def require_app_license(app_key: str) -> Callable:
    """FastAPI 依赖：未授权时返回 402。"""

    async def _dep(db: AsyncSession = Depends(get_db)) -> LicenseState:
        st = await get_license_state(db, app_key)
        if not st.valid:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "LICENSE_REQUIRED",
                    "app_key": app_key,
                    "status": st.status,
                    "message": st.reason or "该应用未授权",
                },
            )
        return st

    return _dep
