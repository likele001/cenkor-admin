"""跨数据库兼容工具（PG 优先，MySQL 5.7+）"""
from __future__ import annotations

from sqlalchemy import JSON, case
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped
from sqlalchemy.sql.elements import ColumnElement

from cenkor_admin.core.config import get_settings


def json_column(**kwargs):
    """PG 使用 JSONB，MySQL 使用 JSON。"""
    settings = get_settings()
    if settings.is_mysql:
        return JSON(**kwargs)
    return JSONB(**kwargs)


def alembic_json():
    """Alembic migration 中使用的 JSON 类型。"""
    from alembic import op
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        return JSON
    from sqlalchemy.dialects import postgresql
    return postgresql.JSONB


def order_nulls_last(column: ColumnElement, *, desc: bool = True) -> list:
    """兼容 PG nullslast 与 MySQL 排序。"""
    settings = get_settings()
    if settings.is_mysql:
        null_rank = case((column.is_(None), 1), else_=0)
        return [null_rank, column.desc() if desc else column.asc()]
    ordered = column.desc() if desc else column.asc()
    return [ordered.nullslast()]
