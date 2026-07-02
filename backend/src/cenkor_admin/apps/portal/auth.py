"""Portal JWT 独立签发（与 admin auth 完全隔离）"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from cenkor_admin.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

PORTAL_JWT_ISSUER = "cenkor-portal"
PORTAL_SECRET_KEY = settings.SECRET_KEY + ":portal"


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
    return jwt.encode(payload, PORTAL_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


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
    return jwt.encode(payload, PORTAL_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_portal_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, PORTAL_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


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
