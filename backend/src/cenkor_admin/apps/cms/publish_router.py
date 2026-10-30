"""内容分发接口。

凭据处理原则：渠道配置里的 AppID / AppSecret 一律加密存库，接口只返回
「尾 4 位」的提示。前端回传掩码值时视为「没改」，避免用户点一次保存就把
密钥覆盖成星号。
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms import analytics_models as am
from cenkor_admin.apps.cms import publish as cms_publish
from cenkor_admin.core.db import get_db
from cenkor_admin.core.secrets import decrypt_secret, encrypt_secret, is_masked_input, secret_hint

log = structlog.get_logger()
router = APIRouter()

# 需要加密的配置键
_SECRET_KEYS = ("appid", "secret", "token", "api_key")


def _mask_config(cfg: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (cfg or {}).items():
        if k in _SECRET_KEYS and isinstance(v, str) and v:
            out[k] = secret_hint(decrypt_secret(v))
        else:
            out[k] = v
    return out


def _merge_config(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """合并配置。掩码值 / 空值不覆盖原值。"""
    merged = dict(old or {})
    for k, v in (new or {}).items():
        if k in _SECRET_KEYS:
            if v is None or (isinstance(v, str) and (not v.strip() or is_masked_input(v))):
                continue  # 没改就保持原密文
            merged[k] = encrypt_secret(str(v))
        else:
            merged[k] = v
    return merged


def _channel_out(c: Any) -> dict[str, Any]:
    handler = cms_publish.CHANNELS.get(c.channel_type)
    return {
        "id": c.id,
        "key": c.channel_key,
        "name": c.name,
        "type": c.channel_type,
        "enabled": c.enabled,
        "is_default": c.is_default,
        "config": _mask_config(c.config or {}),
        "ready": handler is not None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.get("/publish/channels", summary="分发渠道列表")
async def list_channels(
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    channels = await cms_publish.list_channels(db)
    return {
        "items": [_channel_out(c) for c in channels],
        "stats": await cms_publish.job_stats(db),
    }


@router.get("/publish/setup", summary="各渠道接入指引")
async def channel_setup(
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """把「要填什么、去哪拿」写清楚。

    运营不会去看公众号开发文档，他们需要的是「打开哪个页面、复制哪一项」。
    """
    return {
        "builtin": {
            "title": "官网",
            "need": ["站点域名 site_base（用于拼原文链接）"],
            "steps": ["在这里填站点域名，例如 https://blog.cenkor.cn", "发布时会把条目状态推到已发布并派发事件"],
        },
        "webhook": {
            "title": "Webhook 推送",
            "need": ["系统 / Webhook 里至少一个启用的订阅，并勾选 entry.published"],
            "steps": ["去「系统 → Webhook」新增订阅", "事件里勾选 entry.published", "回来点测试确认有接收方"],
        },
        "wechat": {
            "title": "微信公众号",
            "need": ["AppID", "AppSecret", "封面永久素材 thumb_media_id"],
            "steps": [
                "公众号后台 → 设置与开发 → 基本配置，复制 AppID 和 AppSecret",
                "把本服务器公网 IP 加进「IP 白名单」，否则报 40164",
                "素材管理 → 永久素材，上传一张封面，复制 media_id",
                "注意：只建草稿不自动群发，预览确认后由人在后台点发送",
            ],
        },
        "export": {
            "title": "导出（第三方平台）",
            "need": ["无"],
            "steps": [
                "发布时直接产出可粘贴的 HTML / 纯文本 / 封面清单",
                "知乎、百家号支持富文本，粘 HTML 版",
                "头条图文需手动配图；这三个平台都没有开放发布接口，无法自动发",
            ],
        },
    }


@router.patch("/publish/channels/{key}", summary="更新渠道配置")
async def update_channel(
    key: str,
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    channel = await cms_publish.get_channel(db, key)
    if channel is None:
        raise HTTPException(404, "渠道不存在")

    if "enabled" in payload:
        channel.enabled = bool(payload["enabled"])
    if "name" in payload and str(payload["name"]).strip():
        channel.name = str(payload["name"]).strip()[:80]
    if "config" in payload:
        if not isinstance(payload["config"], dict):
            raise HTTPException(400, "config 必须是对象")
        channel.config = _merge_config(channel.config or {}, payload["config"])

    await db.commit()
    await db.refresh(channel)
    log.info("cms.publish.channel_updated", key=key, by=getattr(user, "id", None))
    return _channel_out(channel)


@router.post("/publish/channels/{key}/test", summary="渠道连通性测试")
async def test_channel(
    key: str,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    channel = await cms_publish.get_channel(db, key)
    if channel is None:
        raise HTTPException(404, "渠道不存在")
    handler = cms_publish.CHANNELS.get(channel.channel_type)
    if handler is None:
        raise HTTPException(400, f"渠道类型 {channel.channel_type} 没有实现")
    try:
        result = await handler.test(db, channel)
    except Exception as exc:
        return {"ok": False, "detail": f"测试异常：{exc}"}
    return result


@router.post("/entries/{entry_id}/publish", summary="发布条目到指定渠道")
async def publish_entry(
    entry_id: int,
    payload: dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """一步发布。

    ``{"channels": ["site", "wechat_mp"]}`` —— 不传则所有启用的渠道。
    每个渠道独立返回结果，某个失败不影响其他渠道照常发出。
    """
    keys = payload.get("channels")
    if keys is not None and not isinstance(keys, list):
        raise HTTPException(400, "channels 必须是字符串数组")
    try:
        result = await cms_publish.publish_entry(db, entry_id, keys)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    log.info(
        "cms.publish.done",
        entry_id=entry_id,
        channels=keys,
        by=getattr(user, "id", None),
    )
    return result


@router.get("/publish/jobs", summary="发布任务列表")
async def list_jobs(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    # 用 outerjoin：渠道被删掉之后，历史任务仍然要能看见 ——
    # 否则运营会发现「发布记录凭空少了几条」，其实只是渠道删了。
    stmt = (
        select(am.CmsPublishJob, am.CmsPublishChannel)
        .outerjoin(am.CmsPublishChannel, am.CmsPublishChannel.id == am.CmsPublishJob.channel_id)
        .order_by(am.CmsPublishJob.id.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(am.CmsPublishJob.status == status)
    rows = (await db.execute(stmt)).all()
    return {
        "items": [
            {
                "id": j.id,
                "entry_id": j.entry_id,
                "channel": ch.channel_key if ch else "?",
                "channel_name": ch.name if ch else "(渠道已删除)",
                "status": j.status,
                "attempts": j.attempts,
                "external_id": j.external_id,
                "external_url": j.external_url,
                "error": j.error,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            }
            for j, ch in rows
        ],
        "stats": await cms_publish.job_stats(db),
    }


@router.post("/publish/jobs/{job_id}/retry", summary="重试发布任务")
async def retry_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    job = await db.get(am.CmsPublishJob, job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    # 手动重试清零尝试次数：人明确要求再试一次，就不该被自动重试上限挡住
    job.status = "pending"
    job.attempts = 0
    job.error = None
    await db.commit()
    result = await cms_publish.run_job(db, job)
    return {
        "ok": result.ok,
        "status": job.status,
        "error": result.error,
        "external_url": result.external_url,
        "payload": result.payload,
    }


@router.post("/publish/jobs/run-pending", summary="立即执行待处理任务")
async def run_pending_now(
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    return await cms_publish.run_pending(db, limit=limit)
