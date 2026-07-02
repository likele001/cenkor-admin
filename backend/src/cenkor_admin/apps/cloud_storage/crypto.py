"""凭据 AES-256-GCM 加解密。

复用 platform 已有 SECRET_KEY（settings.SECRET_KEY）派生 32 字节密钥：
    key = SHA256(SECRET_KEY).digest()
密文格式：base64(nonce[12] | ciphertext | tag[16])
"""
from __future__ import annotations

import base64
import hashlib
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from cenkor_admin.core.config import get_settings

settings = get_settings()
_KEY = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        return None  # type: ignore[return-value]
    aes = AESGCM(_KEY)
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt(token: str) -> str:
    if not token:
        return ""
    raw = base64.b64decode(token.encode("ascii"))
    nonce, ct = raw[:12], raw[12:]
    return AESGCM(_KEY).decrypt(nonce, ct, associated_data=None).decode("utf-8")


def mask(value: str, head: int = 3, tail: int = 4) -> str:
    if not value or len(value) <= head + tail:
        return "•" * max(len(value), 6)
    return f"{value[:head]}{'•' * 4}{value[-tail:]}"
