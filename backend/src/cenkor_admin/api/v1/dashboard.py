"""Dashboard 统计端点：总览数字 + 7 天趋势 + 方法分布。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms import models as cms_models
from cenkor_admin.core.audit import AuditLog
from cenkor_admin.core.db import get_db

router = APIRouter()


def _start_of_day_utc(days_ago: int = 0) -> datetime:
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start


@router.get("/stats")
async def dashboard_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """返回 Dashboard 所需的全部数据：

    - 概览数字：users / products / cases / news / media
    - 7 天 API 调用趋势：按天聚合
    - 7 天 HTTP 方法分布：按 method 聚合
    - 7 天状态码分布：2xx / 3xx / 4xx / 5xx
    """
    # 概览数字（软删过滤）
    user_count = (await db.execute(
        select(func.count()).select_from(auth_models.User)
        .where(auth_models.User.deleted_at.is_(None))
    )).scalar() or 0

    product_count = (await db.execute(
        select(func.count()).select_from(cms_models.Product)
        .where(cms_models.Product.deleted_at.is_(None))
    )).scalar() or 0

    case_count = (await db.execute(
        select(func.count()).select_from(cms_models.Case)
        .where(cms_models.Case.deleted_at.is_(None))
    )).scalar() or 0

    news_count = (await db.execute(
        select(func.count()).select_from(cms_models.News)
        .where(cms_models.News.deleted_at.is_(None))
    )).scalar() or 0

    media_count = (await db.execute(
        select(func.count()).select_from(cms_models.Media)
        .where(cms_models.Media.deleted_at.is_(None))
    )).scalar() or 0

    # 7 天趋势起点
    seven_days_ago = _start_of_day_utc(7)

    # 7 天 API 调用趋势（按天）
    daily_rows = (await db.execute(
        select(
            func.date(AuditLog.created_at).label("day"),
            func.count().label("count"),
        )
        .where(AuditLog.created_at >= seven_days_ago)
        .group_by(func.date(AuditLog.created_at))
        .order_by("day")
    )).all()
    daily_map = {str(row.day): int(row.count) for row in daily_rows}

    # 补齐缺失的日期（0 计数）
    trend = []
    for i in range(7, -1, -1):
        day = (_start_of_day_utc(i)).date()
        trend.append({
            "date": day.isoformat(),
            "count": daily_map.get(day.isoformat(), 0),
        })

    # 7 天方法分布
    method_rows = (await db.execute(
        select(AuditLog.method, func.count().label("count"))
        .where(AuditLog.created_at >= seven_days_ago)
        .group_by(AuditLog.method)
    )).all()
    by_method = {row.method: int(row.count) for row in method_rows}

    # 7 天状态码分布（粗粒度：2xx / 3xx / 4xx / 5xx）
    status_rows = (await db.execute(
        select(AuditLog.status_code, func.count().label("count"))
        .where(AuditLog.created_at >= seven_days_ago)
        .group_by(AuditLog.status_code)
    )).all()
    by_status_bucket = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0}
    for row in status_rows:
        sc = int(row.status_code)
        if 200 <= sc < 300:
            by_status_bucket["2xx"] += int(row.count)
        elif 300 <= sc < 400:
            by_status_bucket["3xx"] += int(row.count)
        elif 400 <= sc < 500:
            by_status_bucket["4xx"] += int(row.count)
        elif 500 <= sc < 600:
            by_status_bucket["5xx"] += int(row.count)

    return {
        "overview": {
            "users": int(user_count),
            "products": int(product_count),
            "cases": int(case_count),
            "news": int(news_count),
            "media": int(media_count),
        },
        "api_calls_trend_7d": trend,
        "by_method_7d": by_method,
        "by_status_7d": by_status_bucket,
    }
