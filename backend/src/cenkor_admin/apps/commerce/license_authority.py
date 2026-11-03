"""授权签发侧 —— 私钥生成 + 签名签发（随仓开源，私钥不入库）。

与验签侧的分工：

    cenkor_admin/core/licensing.py          验签 + 状态判断（内置公钥，客户实例必需）
    cenkor_admin/apps/commerce/
      ├── license_authority.py              本文件：私钥生成 + 签名签发
      ├── models.py                         定价 / 订单 / 授权 / 实例绑定
      └── commerce_router.py                云端授权中心 API

安全模型 —— 为什么公开这段代码不影响授权安全：

1. 私钥**不在源码里**。``get_or_create_keypair`` 首次调用时现场生成，
   以密文落进 ``system_settings.license.signing_key``，随部署环境走；
2. 客户实例只内置**公钥**（``core/licensing.DEFAULT_PUBLIC_KEY_B64``）做验签；
3. Ed25519 的安全性只依赖私钥保密，不依赖算法实现保密（Kerckhoffs 原则）——
   拿到全部源码但没有你的私钥，依然伪造不出有效授权。

换句话说，防线是那把私钥，不是这 77 行代码。因此本模块自 v0.5.11 起
随仓开源，与平台同 MIT 授权；自营部署也能自己签发授权，商城功能是完整的。
"""
from __future__ import annotations

import base64
import json
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.core.licensing import get_setting, put_setting

log = structlog.get_logger()

SIGNING_KEY_SETTING = "license.signing_key"


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


async def get_or_create_keypair(db: AsyncSession) -> tuple[str, str]:
    """返回 (私钥 b64url, 公钥 b64url)。仅授权中心调用。"""
    raw = await get_setting(db, SIGNING_KEY_SETTING)
    if raw:
        data = json.loads(raw)
        return data["priv"], data["pub"]

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    priv_b64 = _b64e(priv.private_bytes_raw())
    pub_b64 = _b64e(
        priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )
    await put_setting(
        db,
        SIGNING_KEY_SETTING,
        json.dumps({"priv": priv_b64, "pub": pub_b64}),
        "授权中心 Ed25519 签名密钥（切勿外泄）",
    )
    log.warning("licensing.keypair_created", public_key=pub_b64)
    return priv_b64, pub_b64


async def sign_license_token(db: AsyncSession, payload: dict[str, Any]) -> str:
    """用授权中心私钥签名 payload，返回 ``<b64(payload)>.<b64(sig)>``。"""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv_b64, _ = await get_or_create_keypair(db)
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    priv = Ed25519PrivateKey.from_private_bytes(_b64d(priv_b64))
    sig = priv.sign(body)
    return f"{_b64e(body)}.{_b64e(sig)}"
