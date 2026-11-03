"""通道密钥的对称加密存储。

密文格式：`enc:v1:<fernet-token>`。判据是前缀，明文也能安全混存
（老数据或人工写入的明文不会被误解）。

Fernet key 由 `settings.SECRET_KEY` 经 PBKDF2 派生。**支持密钥轮换**：
签发（加密）永远用最新的 key，解密则依次回退 `SECRET_KEY_OLD` 里的历史 key，
所以换 key 时只要把旧值写进 `SECRET_KEY_OLD`，已存密文即可继续解开。
"""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

import structlog

log = structlog.get_logger()

PREFIX = "enc:v1:"
_SALT = b"cenkor-payment-config-v1"
_ITERATIONS = 120_000


@lru_cache(maxsize=1)
def _fernets() -> tuple:
    """所有有效 key 派生的 Fernet 实例，**最新优先**（索引 0 = 当前签发用）。"""
    from cryptography.fernet import Fernet

    from cenkor_admin.core.config import get_settings

    out = []
    for secret in get_settings().secret_keys:
        raw_secret = (secret or "").encode()
        if not raw_secret:
            continue
        raw = hashlib.pbkdf2_hmac("sha256", raw_secret, _SALT, _ITERATIONS, dklen=32)
        out.append(Fernet(base64.urlsafe_b64encode(raw)))
    if not out:
        log.warning("payment.crypto.no_secret_key")
    return tuple(out)


def is_encrypted(value: object) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt_value(value: str) -> str:
    """加密单个字符串。密钥不可用时原样返回（降级不阻塞业务）。"""
    if not value:
        return ""
    if is_encrypted(value):
        return value
    fernets = _fernets()
    if not fernets:
        return value
    token = fernets[0].encrypt(value.encode()).decode()
    return PREFIX + token


def decrypt_value(value: str) -> str:
    """解密。失败时返回空串（避免把密文当明文用出去）。

    轮换过的旧密文用 `SECRET_KEY_OLD` 里的历史 key 回退解开。
    """
    if not value or not is_encrypted(value):
        return value or ""
    fernets = _fernets()
    if not fernets:
        return ""
    payload = value[len(PREFIX):].encode()
    last_exc: Exception | None = None
    for f in fernets:
        try:
            return f.decrypt(payload).decode()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            continue
    log.warning("payment.crypto.decrypt_failed", error=str(last_exc))
    return ""


def encrypt_config(config: dict, secret_fields: tuple[str, ...]) -> dict:
    """按 secret_fields 加密配置里的敏感项。"""
    out = dict(config or {})
    for key in secret_fields:
        val = out.get(key)
        if isinstance(val, str) and val:
            out[key] = encrypt_value(val)
    return out


def decrypt_config(config: dict, secret_fields: tuple[str, ...]) -> dict:
    """解密出可直接喂给驱动的配置。"""
    out = dict(config or {})
    for key in secret_fields:
        val = out.get(key)
        if isinstance(val, str) and val:
            out[key] = decrypt_value(val)
    return out


def mask_secret(value: str, *, keep: int = 4) -> str:
    """脱敏展示：保留头尾各 keep 位，中间打星。"""
    if not value:
        return ""
    plain = decrypt_value(value) if is_encrypted(value) else value
    if len(plain) <= keep * 2:
        return "*" * len(plain)
    return f"{plain[:keep]}{'*' * 8}{plain[-keep:]}"


def mask_config(config: dict, secret_fields: tuple[str, ...]) -> dict:
    """给前端展示用的脱敏配置，附带 `xxx__set` 标记便于表单显示占位。"""
    out = dict(config or {})
    for key in secret_fields:
        raw = out.get(key)
        if raw:
            out[key] = mask_secret(raw)
            out[f"{key}__set"] = True
    return out
