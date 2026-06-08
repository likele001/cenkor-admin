"""DB session & engine（async 优先，Alembic 用 sync URL）"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from cenkor_admin.core.config import get_settings

settings = get_settings()

# 异步引擎
async_engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    echo=settings.DB_ECHO,
    pool_pre_ping=True,
)

# 会话工厂
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
    autoflush=False,
)


# 全局 Base 之前先 import 所有模型（确保建表顺序）
class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：每个请求一个 session，请求结束自动关闭。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# 类型别名
DBSession = Annotated[AsyncSession, Depends(get_db)]


# 兜底：注册所有模型（import 它们以便 Base.metadata 知道）
def _register_all_models() -> None:
    """注册所有 ORM 模型到 Base.metadata"""
    from cenkor_admin.apps.auth import models as _auth  # noqa
    from cenkor_admin.apps.rbac import models as _rbac  # noqa
    from cenkor_admin.apps.cms import models as _cms  # noqa
    from cenkor_admin.apps.system import models as _system  # noqa
    from cenkor_admin.core.audit import AuditLog  # noqa


_register_all_models()
