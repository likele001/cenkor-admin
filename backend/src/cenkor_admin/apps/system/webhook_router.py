"""Webhook 订阅 & 投递日志 & URL 重定向 管理路由（M3·P2，受保护）

P2 最后一批新增：
- ``GET  /webhook-events``            事件目录（管理端下拉用，带中文说明）
- ``POST /webhooks/{id}/test``        测试发送（不写假条目、不等真实发布就能验证 Agent 连通）
- ``GET  /webhook-deliveries``        投递日志（按订阅/事件/状态过滤 + 分页）
- ``GET  /webhook-deliveries/stats``  近 24h 成败统计
- ``GET  /webhook-deliveries/{id}``   单条详情（含完整 payload）
- ``POST /webhook-deliveries/{id}/replay`` 人工重放
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.system import models
from cenkor_admin.apps.system.webhook_models import WebhookDelivery
from cenkor_admin.core.db import get_db

router = APIRouter()

# 事件目录：key 与投递模块的 WEBHOOK_EVENTS 保持一致
WEBHOOK_EVENT_CATALOG: dict[str, str] = {
    "entry.saved": "内容保存（含草稿，频率高）",
    "entry.published": "内容发布（对外可见，推荐给下游 Agent 用这个）",
    "entry.deleted": "内容删除",
    "content_type.created": "内容类型创建",
    "media.uploaded": "媒体上传",
    "user.login": "用户登录",
}
WEBHOOK_EVENTS = tuple(WEBHOOK_EVENT_CATALOG)


# ============================================================
# Webhook 订阅
# ============================================================

@router.get("/webhook-events", response_model=dict[str, Any])
async def list_webhook_events():
    return {
        "items": [{"key": k, "label": v} for k, v in WEBHOOK_EVENT_CATALOG.items()],
        "total": len(WEBHOOK_EVENT_CATALOG),
    }


@router.get("/webhooks", response_model=dict[str, Any])
async def list_webhooks(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(models.Webhook).order_by(models.Webhook.id.desc())
    )).scalars().all()
    # 每个订阅带一条「最近一次投递」概要，列表页不用来回查
    last: dict[int, WebhookDelivery] = {}
    if rows:
        ids = [w.id for w in rows]
        recent = (await db.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.webhook_id.in_(ids))
            .order_by(WebhookDelivery.id.desc())
            .limit(200)
        )).scalars().all()
        for d in recent:
            if d.webhook_id not in last:
                last[d.webhook_id] = d
    out = []
    for w in rows:
        item = _wh_dict(w)
        item["last_delivery"] = _delivery_brief(last.get(w.id))
        out.append(item)
    return {"items": out, "total": len(out)}


@router.post("/webhooks", response_model=dict[str, Any], status_code=201)
async def create_webhook(body: dict, db: AsyncSession = Depends(get_db)):
    url = body.get("url")
    events = body.get("events") or []
    if not url:
        raise HTTPException(400, "url required")
    invalid = [e for e in events if e not in WEBHOOK_EVENTS]
    if invalid:
        raise HTTPException(400, f"非法事件: {invalid}，可用: {list(WEBHOOK_EVENTS)}")
    obj = models.Webhook(
        url=url, events=events, secret=body.get("secret"),
        description=body.get("description"), enabled=body.get("enabled", True),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _wh_dict(obj)


@router.patch("/webhooks/{wh_id}", response_model=dict[str, Any])
async def update_webhook(wh_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    obj = await db.get(models.Webhook, wh_id)
    if not obj:
        raise HTTPException(404, "Webhook not found")
    if "events" in body:
        invalid = [e for e in body["events"] if e not in WEBHOOK_EVENTS]
        if invalid:
            raise HTTPException(400, f"非法事件: {invalid}")
    for k in ("url", "events", "secret", "description", "enabled"):
        if k in body:
            setattr(obj, k, body[k])
    await db.commit()
    await db.refresh(obj)
    return _wh_dict(obj)


@router.delete("/webhooks/{wh_id}", status_code=204)
async def delete_webhook(wh_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(models.Webhook, wh_id)
    if not obj:
        raise HTTPException(404, "Webhook not found")
    await db.delete(obj)
    await db.commit()


@router.post("/webhooks/{wh_id}/test", response_model=dict[str, Any])
async def test_webhook(wh_id: int, db: AsyncSession = Depends(get_db)):
    """测试发送：不管订阅里勾了什么事件，直接投一条 ``webhook.test``。"""
    obj = await db.get(models.Webhook, wh_id)
    if not obj:
        raise HTTPException(404, "Webhook not found")
    if not obj.enabled:
        raise HTTPException(400, "订阅已停用，先启用再测试")

    from cenkor_admin.apps.system import webhooks as wh

    ids = await wh.enqueue("webhook.test", {
        "message": "这是一条测试投递，由管理端手动触发",
        "webhook_id": obj.id,
        "url": obj.url,
    }, webhook_ids=[obj.id])
    return {"queued": len(ids), "delivery_ids": ids}


def _wh_dict(w: models.Webhook) -> dict:
    return {
        "id": w.id, "url": w.url, "events": w.events or [],
        "secret": w.secret, "description": w.description, "enabled": w.enabled,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


# ============================================================
# 投递日志
# ============================================================
# 注意顺序：``stats`` 必须声明在 ``{did}`` 之前，否则会被当成路径参数解析成 int 失败。

@router.get("/webhook-deliveries/stats", response_model=dict[str, Any])
async def delivery_stats(hours: int = Query(24, ge=1, le=720), db: AsyncSession = Depends(get_db)):
    since = datetime.now(UTC) - timedelta(hours=hours)
    rows = (await db.execute(
        select(WebhookDelivery.status, func.count())
        .where(WebhookDelivery.created_at >= since)
        .group_by(WebhookDelivery.status)
    )).all()
    by_status = {s: int(c) for s, c in rows}
    total = sum(by_status.values())
    ok = by_status.get("success", 0)
    return {
        "hours": hours,
        "total": total,
        "by_status": by_status,
        "success_rate": round(ok / total, 4) if total else None,
    }


@router.get("/webhook-deliveries", response_model=dict[str, Any])
async def list_deliveries(
    webhook_id: int | None = Query(None),
    event: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    conds = []
    if webhook_id:
        conds.append(WebhookDelivery.webhook_id == webhook_id)
    if event:
        conds.append(WebhookDelivery.event == event)
    if status:
        conds.append(WebhookDelivery.status == status)

    total = (await db.execute(
        select(func.count()).select_from(WebhookDelivery).where(*conds)
    )).scalar_one()
    rows = (await db.execute(
        select(WebhookDelivery)
        .where(*conds)
        .order_by(WebhookDelivery.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()
    return {
        "items": [_delivery_brief(d) for d in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@router.get("/webhook-deliveries/{did}", response_model=dict[str, Any])
async def get_delivery(did: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(WebhookDelivery, did)
    if obj is None:
        raise HTTPException(404, "投递记录不存在")
    data = _delivery_brief(obj)
    data["payload"] = obj.payload
    return data


@router.post("/webhook-deliveries/{did}/replay", response_model=dict[str, Any])
async def replay_delivery(did: int, db: AsyncSession = Depends(get_db)):
    """重放：event_id 保持不变，下游按 X-Cenkor-Event-Id 幂等即可。"""
    from cenkor_admin.apps.system import webhooks as wh

    obj = await db.get(WebhookDelivery, did)
    if obj is None:
        raise HTTPException(404, "投递记录不存在")
    ok = await wh.replay(did)
    # replay 用的是另一个 session，本 session 里这条对象是旧的，必须过期重读
    await db.refresh(obj)
    return {"ok": ok, "delivery": _delivery_brief(obj)}


def _delivery_brief(d: WebhookDelivery | None) -> dict | None:
    if d is None:
        return None
    return {
        "id": d.id,
        "event_id": d.event_id,
        "webhook_id": d.webhook_id,
        "event": d.event,
        "url": d.url,
        "status": d.status,
        "attempts": d.attempts,
        "http_status": d.http_status,
        "response_snippet": d.response_snippet,
        "error": d.error,
        "duration_ms": d.duration_ms,
        "next_retry_at": d.next_retry_at.isoformat() if d.next_retry_at else None,
        "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


# ============================================================
# URL 重定向
# ============================================================

@router.get("/redirects", response_model=dict[str, Any])
async def list_redirects(db: AsyncSession = Depends(get_db), search: str | None = Query(None)):
    stmt = select(models.Redirect).order_by(models.Redirect.id.desc())
    if search:
        stmt = stmt.where(
            models.Redirect.from_path.ilike(f"%{search}%")
            | models.Redirect.to_path.ilike(f"%{search}%")
        )
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [_rd_dict(r) for r in rows], "total": len(rows)}


@router.post("/redirects", response_model=dict[str, Any], status_code=201)
async def create_redirect(body: dict, db: AsyncSession = Depends(get_db)):
    from_path = (body.get("from_path") or "").strip()
    to_path = (body.get("to_path") or "").strip()
    if not from_path or not to_path:
        raise HTTPException(400, "from_path 与 to_path 必填")
    existing = await db.execute(
        select(models.Redirect).where(models.Redirect.from_path == from_path)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"from_path 已存在: {from_path}")
    obj = models.Redirect(
        from_path=from_path, to_path=to_path,
        code=body.get("code", 301), enabled=body.get("enabled", True),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    from cenkor_admin.core.redirects import clear_redirect_cache
    clear_redirect_cache()
    return _rd_dict(obj)


@router.patch("/redirects/{rid}", response_model=dict[str, Any])
async def update_redirect(rid: int, body: dict, db: AsyncSession = Depends(get_db)):
    obj = await db.get(models.Redirect, rid)
    if not obj:
        raise HTTPException(404, "Redirect not found")
    for k in ("from_path", "to_path", "code", "enabled"):
        if k in body:
            setattr(obj, k, body[k])
    await db.commit()
    await db.refresh(obj)
    from cenkor_admin.core.redirects import clear_redirect_cache
    clear_redirect_cache()
    return _rd_dict(obj)


@router.delete("/redirects/{rid}", status_code=204)
async def delete_redirect(rid: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(models.Redirect, rid)
    if not obj:
        raise HTTPException(404, "Redirect not found")
    await db.delete(obj)
    await db.commit()
    from cenkor_admin.core.redirects import clear_redirect_cache
    clear_redirect_cache()


def _rd_dict(r: models.Redirect) -> dict:
    return {
        "id": r.id, "from_path": r.from_path, "to_path": r.to_path,
        "code": r.code, "enabled": r.enabled,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
