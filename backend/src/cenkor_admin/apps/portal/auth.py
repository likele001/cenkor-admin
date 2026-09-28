"""Portal JWT 独立签发（与 admin auth 完全隔离，支持 SECRET_KEY 轮换）"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from cenkor_admin.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

PORTAL_JWT_ISSUER = "cenkor-portal"
_PORTAL_SUFFIX = ":portal"


def _portal_keys() -> list[str]:
    """所有有效的 portal 签名密钥（最新优先）。

    与 `core.security.decode_token` 同语义：签发用最新的，校验依次回退历史 key。
    这样轮换 `SECRET_KEY`（配 `SECRET_KEY_OLD`）不会让已登录的开发者掉线。
    """
    return [f"{k}{_PORTAL_SUFFIX}" for k in settings.secret_keys]


def __getattr__(name: str) -> Any:
    """兼容旧引用：`PORTAL_SECRET_KEY` 仍可读，返回当前最新密钥。"""
    if name == "PORTAL_SECRET_KEY":
        return _portal_keys()[0]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_portal_access_token(
    subject: str | int,
    extra: dict[str, Any] | None = None,
    expires_minutes: int | None = None,
) -> str:
    minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": "access",
        "iss": PORTAL_JWT_ISSUER,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, _portal_keys()[0], algorithm=settings.JWT_ALGORITHM)


def create_portal_refresh_token(subject: str | int, token_version: int = 0) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "type": "refresh",
        "iss": PORTAL_JWT_ISSUER,
        "tv": token_version,
        "iat": now,
        "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, _portal_keys()[0], algorithm=settings.JWT_ALGORITHM)


def decode_portal_token(token: str) -> dict[str, Any]:
    """解码并校验 portal token。失败抛 JWTError。

    支持 SECRET_KEY 轮换：依次尝试所有有效 key（最新的优先）。
    """
    last_err: Exception | None = None
    for key in _portal_keys():
        try:
            return jwt.decode(token, key, algorithms=[settings.JWT_ALGORITHM])
        except JWTError as e:
            last_err = e
            continue
    if last_err:
        raise last_err
    raise JWTError("No valid SECRET_KEY configured")


def is_portal_token(payload: dict[str, Any]) -> bool:
    return payload.get("iss") == PORTAL_JWT_ISSUER


__all__ = [
    "hash_password",
    "verify_password",
    "create_portal_access_token",
    "create_portal_refresh_token",
    "decode_portal_token",
    "is_portal_token",
    "PORTAL_JWT_ISSUER",
    "JWTError",
]
