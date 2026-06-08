"""Redis 客户端"""
from __future__ import annotations

import redis.asyncio as redis
from cenkor_admin.core.config import get_settings

settings = get_settings()

redis_client: redis.Redis = redis.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
    health_check_interval=30,
)
