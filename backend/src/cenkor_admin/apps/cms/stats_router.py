"""内容效果接口（看板 + 回填共用）。

挂在 ``/cms/ai/stats`` 下而不是新建 ``/cms/stats``：统计看板本来就是
AI CMS 的一部分（选题和质检都要吃这些数据），复用 ``cms:ai:read`` 权限
比新开一套权限点更省事，也不会让运营配漏权限。

接口数量刻意压到 6 个：总览接口一次返回「数字 + 趋势 + 渠道」，前端不用
并发拼四个请求，弱网下也不会出现半屏有数半屏空着。
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms import stats as cms_stats
from cenkor_admin.apps.cms import tracking
from cenkor_admin.core.db import get_db

log = structlog.get_logger()
router = APIRouter()


@router.get("/stats/overview", summary="效果总览（含趋势与渠道）")
async def stats_overview(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "overview": await cms_stats.overview(db, days=days),
        "trend": await cms_stats.daily_trend(db, days=days),
        "channels": await cms_stats.channel_breakdown(db, days=days),
        "storage": await tracking.track_storage_stats(db),
    }


@router.get("/stats/entries", summary="内容表现排行（带可解释理由）")
async def stats_entries(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    min_pv: int = Query(default=1, ge=0),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    items = await cms_stats.entry_performance(db, days=days, limit=limit, min_pv=min_pv)
    return {"items": items, "days": days, "count": len(items)}


@router.get("/stats/insights", summary="效果回填结论：低效内容 / 零流量 / 主题权重")
async def stats_insights(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """这三个列表就是「数据说了算」的全部产出。

    - ``low_performers``：有流量但没人读完 → 改标题或改开头
    - ``dead_content``：发布很久零访问 → 没分发出去，不是内容问题
    - ``topics``：哪类主题实际表现好 → 下一篇写什么
    """
    return {
        "low_performers": await cms_stats.low_performers(db, days=days),
        "dead_content": await cms_stats.dead_content(db, days=7),
        "topics": await cms_stats.topic_weights(db, days=max(days, 90)),
    }


@router.post("/stats/refresh", summary="手动重算汇总")
async def stats_refresh(
    days: int = Query(default=7, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """口径调整后重算历史。汇总表是「整天覆盖写」，重复执行安全。"""
    result = await cms_stats.aggregate_range(db, days=days)
    synced = await cms_stats.sync_view_count(db)
    return {**result, "view_count_synced": synced}


@router.post("/stats/import", summary="导入第三方统计数据")
async def stats_import(
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """接入百度统计 / GA / 人工表的统一入口。

    ``{"source": "baidu", "rows": [{"entry_id": 1190, "date": "2026-10-29",
    "pv": 120, "uv": 88, ...}]}``

    外部数据与自建埋点并存（不同 source），不互相覆盖。两边口径本来就
    不一样，合并只会得到一个谁都不认的数字。
    """
    source = str(payload.get("source") or "")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise HTTPException(400, "rows 不能为空")
    if source not in ("baidu", "ga", "manual"):
        raise HTTPException(400, "source 必须是 baidu / ga / manual")
    try:
        return await cms_stats.import_external_stats(db, rows=rows, source=source)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/stats/tracking-setup", summary="埋点接入指引")
async def tracking_setup(
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """给运营看的接入说明。技术细节藏在这里，页面上只显示要复制的那一行。"""
    return {
        "snippet": '<script src="https://admin.cenkor.cn/api/v1/public/track.js" data-site="1" defer></script>',
        "notes": [
            "把这段放到官网模板 </head> 前，全站一次即可，不用改业务代码。",
            "内容 ID 会自动按 URL 里的 slug 反查，不需要在模板里写 meta 标签。",
            "需要手动指定内容时，用 data-entry=\"1214\" 或 <meta name=\"cms-entry-id\" content=\"1214\">。",
            "要统计线索转化，在提交成功的回调里调 window.cmsTrack.convert('lead', 1)。",
            "数据在「内容效果」页查看，明细留在 cms_track_events，保留 90 天。",
        ],
        "events": list(tracking.EVENT_TYPES),
        "quota_per_ip_per_day": tracking.IP_DAILY_QUOTA,
    }
