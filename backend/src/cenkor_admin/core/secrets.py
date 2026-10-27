"""密钥加解密 · 供后台可视化配置的 API Key 落库使用。

为什么必须加密：AI_API_KEY 迁到数据库后，它会出现在 pg_dump、数据库备份、
只读账号查询结果、甚至运维随手 ``SELECT *`` 的终端滚动里。明文存储等于把
服务商账单权限散落各处，是典型的低成本高损失风险。

密钥来源：复用 ``SECRET_KEY`` 经 HMAC-SHA256 派生 32 字节做 Fernet key，
不引入新配置项。轮换 SECRET_KEY 会导致旧密文无法解开——这是预期行为，
解密失败返回 None 而不是抛异常，让上层降级为「该服务商未配置密钥」。
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken

from cenkor_admin.core.config import get_settings

# 密文前缀。带版本号，将来换算法可以按前缀分流解密。
PREFIX = "enc:v1:"
# 派生上下文的固定盐。改它会作废所有历史密文，不要动。
_HKDF_INFO = b"cenkor-ai-provider-key-v1"


def _fernet() -> Fernet:
    secret = (get_settings().SECRET_KEY or "").encode("utf-8")
    digest = hmac.new(secret, _HKDF_INFO, hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str | None) -> str:
    """加密。空值返回空串；已是密文则原样返回（幂等，便于重复保存）。"""
    if not plain:
        return ""
    if plain.startswith(PREFIX):
        return plain
    return PREFIX + _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str | None) -> str | None:
    """解密。

    返回 None 表示「密文存在但解不开」（SECRET_KEY 变了），
    上层应视为该服务商未配置密钥并给出可操作的提示；
    没有前缀的旧值是历史明文（从 .env 迁移而来），原样返回。
    """
    if not token:
        return ""
    if not token.startswith(PREFIX):
        return token
    try:
        return _fernet().decrypt(token[len(PREFIX) :].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def secret_hint(plain: str | None) -> str:
    """生成掩码展示串，如 ``sk-...a1b2``。

    只暴露长度与末四位：够用户确认「填的是哪把 key」，不足以复原。
    短于 8 位的直接全掩码，避免掩码本身泄露全部内容。
    """
    if not plain:
        return ""
    tail = plain[-4:]
    if len(plain) <= 8:
        return "****"
    return f"****{tail}"


def is_masked_input(value: str | None) -> bool:
    """判断前端提交的是不是掩码占位串。

    编辑场景里前端拿到的是 ``****a1b2``，用户不修改就会原样回传。
    必须识别出来并当作「不修改密钥」，否则会把掩码存成真密钥。
    """
    if not value:
        return False
    return value.startswith("****") or set(value) <= {"*"}


def secret_fingerprint(plain: str | None) -> str:
    """不可逆指纹，用于「同一把 key 是否重复填写」这类比对，不含原文。"""
    if not plain:
        return ""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()[:16]
