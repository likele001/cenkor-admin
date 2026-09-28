"""凭据 AES-256-GCM 加解密。

复用 platform 已有 SECRET_KEY（settings.SECRET_KEY）派生 32 字节密钥：
    key = SHA256(SECRET_KEY).digest()
密文格式：base64(nonce[12] | ciphertext | tag[16])

**支持密钥轮换**：加密用最新 key，解密依次回退 `SECRET_KEY_OLD` 里的历史 key。
"""
from __future__ import annotations

import base64
import hashlib
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from cenkor_admin.core.config import get_settings

settings = get_settings()


def _keys() -> tuple[bytes, ...]:
    """所有有效 key 的派生结果，**最新优先**（索引 0 = 当前加密用）。"""
    out = []
    for k in settings.secret_keys:
        if not k:
            continue
        out.append(hashlib.sha256(k.encode("utf-8")).digest())
    return tuple(out)


# 兼容旧引用：当前（最新）密钥的派生值
_KEY = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        return None  # type: ignore[return-value]
    keys = _keys()
    if not keys:
        raise ValueError("No SECRET_KEY configured")
    aes = AESGCM(keys[0])
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt(token: str) -> str:
    if not token:
        return ""
    raw = base64.b64decode(token.encode("ascii"))
    nonce, ct = raw[:12], raw[12:]
    last_exc: Exception | None = None
    for key in _keys():
        try:
            return AESGCM(key).decrypt(nonce, ct, associated_data=None).decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            continue
    if last_exc is not None:
        raise last_exc
    raise ValueError("No SECRET_KEY configured")


def mask(value: str, head: int = 3, tail: int = 4) -> str:
    if not value or len(value) <= head + tail:
        return "•" * max(len(value), 6)
    return f"{value[:head]}{'•' * 4}{value[-tail:]}"
