"""内容分发：把「审核通过的内容」推到各个出口。

四个渠道，能力边界如实划清：

- **官网**：内置。真正的工作是把条目状态推到 published 并派发
  ``entry.published`` 事件 —— 事件才是下游（静态站重建、CDN 刷新、
  搜索推送）的触发点，比直接改个字段有用得多。
- **Webhook**：复用 ``apps.system.webhooks``，不另造推送。
- **微信公众号**：走草稿箱接口（``draft/add``）。只建草稿不自动群发 ——
  群发是不可撤销的，机器不该替人按那个按钮。
- **导出**：知乎 / 头条 / 百家号这类**没有开放发布接口**的平台。
  这里生成可直接粘贴的 HTML + 封面清单，人工发。
  不做假的「自动发布」：假装能自动发，最后还是要人去点，不如老实说。

每个渠道一条任务、独立重试。公众号 Secret 配错不该把官网发布一起拖死。
"""

from __future__ import annotations

import html as html_lib
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import analytics_models as am
from cenkor_admin.apps.cms import models as cms_models
from cenkor_admin.core.secrets import decrypt_secret

log = structlog.get_logger()

MAX_ATTEMPTS = 3

WECHAT_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
WECHAT_DRAFT_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"

# 公众号错误码 → 人话。运营看到「40013」只会去问开发，
# 看到「AppID 不对」自己去改就行了。
WECHAT_ERRORS = {
    40001: "AppSecret 不正确，或已被重置",
    40013: "AppID 不正确",
    40125: "AppSecret 无效，请到公众平台重置",
    40164: "服务器 IP 不在公众号白名单，请把本机公网 IP 加进去",
    45003: "标题超出长度限制",
    45009: "接口调用次数超限，今天请勿再试",
    48001: "该公众号没有草稿箱接口权限（订阅号未认证会这样）",
    53404: "账号已被限制，无法调用该接口",
}

# access_token 进程内缓存。有效期 7200 秒，提前 200 秒过期避免边界失败。
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_TOKEN_TTL = 7000.0

_HEADING_KEYS = ("html", "body", "content", "text", "markdown", "md")


@dataclass
class PublishResult:
    ok: bool
    external_id: str | None = None
    external_url: str | None = None
    error: str | None = None
    skipped: bool = False
    payload: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 正文提取
# ---------------------------------------------------------------------------


def entry_body(entry: Any) -> str:
    """从 ``entry.content`` 里取正文。

    内容结构是 JSON、字段名随内容类型变（富文本用 html、Markdown 站点用
    markdown、老数据直接塞纯文本）。这里按常见键依次试，取到第一个非空
    的就用，不做严格 schema 校验 —— 严格校验的结果是运营建个新内容类型
    就发不出去。
    """
    content = getattr(entry, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, dict):
        for key in _HEADING_KEYS:
            val = content.get(key)
            if isinstance(val, str) and val.strip():
                return val
        # 再退一步：把所有字符串字段拼起来，至少不会发出去一片空白
        parts = [v for v in content.values() if isinstance(v, str) and v.strip()]
        if parts:
            return "\n\n".join(parts)
    custom = getattr(entry, "custom_fields", None)
    if isinstance(custom, dict):
        for key in _HEADING_KEYS:
            val = custom.get(key)
            if isinstance(val, str) and val.strip():
                return val
    return ""


def plain_text(entry: Any, limit: int = 300) -> str:
    body = re.sub(r"<[^>]+>", " ", entry_body(entry))
    body = re.sub(r"\s+", " ", body).strip()
    summary = ""
    seo = getattr(entry, "seo", None)
    if isinstance(seo, dict):
        summary = str(seo.get("description") or "").strip()
    return (summary or body)[:limit]


def _channel_config(channel: Any) -> dict[str, Any]:
    cfg = getattr(channel, "config", None)
    return cfg if isinstance(cfg, dict) else {}


def _site_base(channel: Any) -> str:
    return str(_channel_config(channel).get("site_base") or "").rstrip("/")


def entry_url(entry: Any, channel: Any) -> str | None:
    """拼对外地址。没配站点域名就返回 None —— 宁可没有链接，也不要给个假链接。"""
    base = _site_base(channel)
    slug = getattr(entry, "slug", None)
    if not base or not slug:
        return None
    return f"{base}/{str(slug).lstrip('/')}"


# ---------------------------------------------------------------------------
# 渠道适配器
# ---------------------------------------------------------------------------


class BaseChannel:
    channel_type = ""

    async def publish(self, db: AsyncSession, entry: Any, channel: Any) -> PublishResult:
        raise NotImplementedError

    async def test(self, db: AsyncSession, channel: Any) -> dict[str, Any]:
        return {"ok": True, "detail": "该渠道无需测试"}


CHANNELS: dict[str, BaseChannel] = {}


def register(cls: type[BaseChannel]) -> type[BaseChannel]:
    CHANNELS[cls.channel_type] = cls()
    return cls


@register
class SiteChannel(BaseChannel):
    """官网。

    幂等：已经 published 的条目再发一次返回 skipped，不重复派发事件 ——
    否则下游的静态站重建、CDN 刷新会被重复触发，白花钱。
    """

    channel_type = "builtin"

    async def publish(self, db: AsyncSession, entry: Any, channel: Any) -> PublishResult:
        now = datetime.now(UTC)
        if getattr(entry, "status", "") == "published" and getattr(entry, "published_at", None):
            return PublishResult(
                ok=True,
                skipped=True,
                external_url=entry_url(entry, channel),
                payload={"reason": "条目已是发布状态，跳过重复发布"},
            )

        entry.status = "published"
        entry.published_at = entry.published_at or now
        await db.commit()

        # 事件派发是这步真正的作用：下游靠它知道「有新内容上线了」
        try:
            from cenkor_admin.core.hooks import dispatch

            await dispatch("entry.published", entry=entry, db=db, user=None)
        except Exception as exc:
            log.warning("cms.publish.dispatch_failed", entry_id=entry.id, error=str(exc))

        return PublishResult(
            ok=True,
            external_id=f"entry:{entry.id}",
            external_url=entry_url(entry, channel),
            payload={"published_at": now.isoformat()},
        )


@register
class WebhookChannel(BaseChannel):
    """Webhook 推送。复用 system.webhooks 的投递日志与重试。"""

    channel_type = "webhook"

    async def publish(self, db: AsyncSession, entry: Any, channel: Any) -> PublishResult:
        from cenkor_admin.apps.system import webhooks

        data = await webhooks._entry_data(entry, db)
        ids = await webhooks.enqueue("entry.published", data)
        if not ids:
            return PublishResult(
                ok=False,
                error="没有启用的 Webhook 订阅，请先在「系统 / Webhook」里添加并勾选 entry.published",
            )
        return PublishResult(
            ok=True,
            external_id="delivery:" + ",".join(str(i) for i in ids),
            payload={"deliveries": ids},
        )

    async def test(self, db: AsyncSession, channel: Any) -> dict[str, Any]:
        from cenkor_admin.apps.system import models as sys_models

        rows = (
            await db.execute(
                select(sys_models.Webhook).where(sys_models.Webhook.enabled.is_(True))
            )
        ).scalars().all()
        matched = [w for w in rows if "entry.published" in (w.events or [])]
        return {
            "ok": bool(matched),
            "detail": (
                f"已启用且订阅 entry.published 的 Webhook：{len(matched)} 个"
                if matched
                else "没有启用的 Webhook 订阅 entry.published，推送会无接收方"
            ),
        }


@register
class WechatChannel(BaseChannel):
    """微信公众号草稿箱。

    刻意只建草稿、不群发：群发不可撤销，发错一篇文章影响的是品牌。
    机器负责把排版和封面准备好，最后那下由人在公众号后台点。

    封面 ``thumb_media_id`` 必须是**永久素材**的 media_id，这是接口的硬要求。
    没配就在错误信息里说清楚怎么拿，而不是抛一个 40007 让人猜。
    """

    channel_type = "wechat"

    def _cfg(self, channel: Any) -> dict[str, Any]:
        cfg = channel.config if isinstance(channel.config, dict) else {}
        return {
            "appid": decrypt_secret(cfg.get("appid")) or "",
            "secret": decrypt_secret(cfg.get("secret")) or "",
            "thumb_media_id": cfg.get("thumb_media_id") or "",
            "author": cfg.get("author") or "",
            "source_url": cfg.get("source_url") or "",
        }

    async def _token(self, appid: str, secret: str) -> str:
        key = f"{appid}:{secret[:8]}"
        hit = _TOKEN_CACHE.get(key)
        now = time.monotonic()
        if hit and now - hit[1] < _TOKEN_TTL:
            return hit[0]

        import httpx

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                WECHAT_TOKEN_URL,
                params={"grant_type": "client_credential", "appid": appid, "secret": secret},
            )
        data = resp.json()
        token = data.get("access_token")
        if not token:
            code = data.get("errcode")
            raise RuntimeError(f"获取 access_token 失败（{code}）：{WECHAT_ERRORS.get(code, data.get('errmsg') or '未知错误')}")
        _TOKEN_CACHE[key] = (token, now)
        return token

    async def publish(self, db: AsyncSession, entry: Any, channel: Any) -> PublishResult:
        cfg = self._cfg(channel)
        if not cfg["appid"] or not cfg["secret"]:
            return PublishResult(ok=False, error="公众号未配置 AppID / AppSecret")
        if not cfg["thumb_media_id"]:
            return PublishResult(
                ok=False,
                error=(
                    "缺少封面素材 ID。公众号草稿接口要求 thumb_media_id，"
                    "请到公众号后台「素材管理 → 永久素材」上传一张封面，"
                    "再把返回的 media_id 填进渠道配置。"
                ),
            )

        import httpx

        try:
            token = await self._token(cfg["appid"], cfg["secret"])
            article = {
                "title": (getattr(entry, "title", "") or "")[:64],
                "author": cfg["author"][:16],
                "digest": plain_text(entry, 120),
                "content": entry_body(entry) or "<p></p>",
                "content_source_url": cfg["source_url"] or entry_url(entry, channel) or "",
                "thumb_media_id": cfg["thumb_media_id"],
                "need_open_comment": 0,
                "only_fans_can_comment": 0,
            }
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    WECHAT_DRAFT_URL,
                    params={"access_token": token},
                    json={"articles": [article]},
                )
            data = resp.json()
            if data.get("media_id"):
                return PublishResult(
                    ok=True,
                    external_id=str(data["media_id"]),
                    payload={"note": "已建草稿，请到公众号后台预览确认后群发"},
                )
            code = data.get("errcode")
            # token 失效时清缓存，下次重试会重新取
            if code in (40001, 42001):
                _TOKEN_CACHE.pop(f"{cfg['appid']}:{cfg['secret'][:8]}", None)
            return PublishResult(
                ok=False,
                error=f"建草稿失败（{code}）：{WECHAT_ERRORS.get(code, data.get('errmsg') or '未知错误')}",
            )
        except Exception as exc:
            return PublishResult(ok=False, error=f"公众号调用异常：{exc}")

    async def test(self, db: AsyncSession, channel: Any) -> dict[str, Any]:
        cfg = self._cfg(channel)
        if not cfg["appid"] or not cfg["secret"]:
            return {"ok": False, "detail": "未配置 AppID / AppSecret"}
        try:
            await self._token(cfg["appid"], cfg["secret"])
        except Exception as exc:
            return {"ok": False, "detail": str(exc)}
        extra = "" if cfg["thumb_media_id"] else "（但还缺封面 thumb_media_id，实际发布会失败）"
        return {"ok": True, "detail": f"access_token 获取成功{extra}"}


@register
class ExportChannel(BaseChannel):
    """导出给第三方平台。

    知乎、头条、百家号都没有开放的内容发布接口。能做的是把内容整理成
    「复制过去就能用」的形态：干净 HTML + 纯文本 + 标题 + 摘要 + 封面。
    不伪装成自动发布 —— 假装能自动发，最后还是要人去点，那不如老实说。
    """

    channel_type = "export"

    async def publish(self, db: AsyncSession, entry: Any, channel: Any) -> PublishResult:
        title = getattr(entry, "title", "") or ""
        body = entry_body(entry)
        digest = plain_text(entry, 300)
        url = entry_url(entry, channel)

        text = re.sub(r"<[^>]+>", "\n", body)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        page = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{html_lib.escape(title)}</title></head>
<body><h1>{html_lib.escape(title)}</h1>
{body}
<hr><p>原文链接：{html_lib.escape(url or '（未配置站点域名）')}</p>
</body></html>"""

        return PublishResult(
            ok=True,
            external_id=f"export:{entry.id}",
            external_url=url,
            payload={
                "title": title,
                "digest": digest,
                "html": page,
                "plain": text,
                "cover": _cover_of(entry),
                "howto": [
                    "复制上面的 HTML 粘贴到支持富文本的编辑器（知乎、百家号支持）",
                    "纯文本版给只收文本的平台（头条图文需手动配图）",
                    "封面图单独上传，不要指望平台自动抓取",
                ],
            },
        )


def _cover_of(entry: Any) -> str | None:
    for attr in ("cover_url", "cover", "thumbnail"):
        val = getattr(entry, attr, None)
        if isinstance(val, str) and val:
            return val
    seo = getattr(entry, "seo", None)
    if isinstance(seo, dict):
        for key in ("og_image", "image", "cover"):
            val = seo.get(key)
            if isinstance(val, str) and val:
                return val
    return None


# ---------------------------------------------------------------------------
# 任务编排
# ---------------------------------------------------------------------------


async def list_channels(db: AsyncSession, *, enabled_only: bool = False) -> list[Any]:
    stmt = select(am.CmsPublishChannel).order_by(am.CmsPublishChannel.id)
    if enabled_only:
        stmt = stmt.where(am.CmsPublishChannel.enabled.is_(True))
    return list((await db.execute(stmt)).scalars().all())


async def get_channel(db: AsyncSession, key: str) -> Any | None:
    return (
        await db.execute(
            select(am.CmsPublishChannel).where(am.CmsPublishChannel.channel_key == key)
        )
    ).scalar_one_or_none()


async def enqueue(
    db: AsyncSession, entry_id: int, channel_keys: list[str] | None = None
) -> tuple[list[int], list[str]]:
    """为条目创建发布任务，返回 ``(任务 ID 列表, 不存在的渠道名列表)``。

    ``channel_keys`` 显式指定时**不看 enabled 开关**：人明确说「这篇发到
    公众号」，就该发。``enabled`` 是「默认发哪些」的偏好，不是权限门禁。
    如果按 enabled 过滤，运营想临时发一次公众号就先得去改全局开关，
    发完再改回来 —— 这种设计只会让人绕过它。

    渠道名写错则如实报出来，不静默跳过：否则调用方会以为发出去了。
    """
    all_channels = await list_channels(db)
    if channel_keys:
        wanted = list(dict.fromkeys(channel_keys))  # 去重且保序
        by_key = {c.channel_key: c for c in all_channels}
        channels = [by_key[k] for k in wanted if k in by_key]
        missing = [k for k in wanted if k not in by_key]
        if missing:
            log.warning("cms.publish.unknown_channel", keys=missing)
    else:
        channels = [c for c in all_channels if c.enabled]
        missing = []

    if not channels:
        return [], missing

    # 用 RETURNING 拿主键，而不是插完再查「最近 N 条」——
    # 后者在并发发布时会抓到别人的任务。
    ids: list[int] = []
    table = am.CmsPublishJob.__table__
    for c in channels:
        res = await db.execute(
            table.insert()
            .values(
                entry_id=entry_id,
                channel_id=c.id,
                status="pending",
                attempts=0,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            .returning(table.c.id)
        )
        ids.append(int(res.scalar_one()))
    await db.commit()
    return ids, missing


async def run_job(db: AsyncSession, job: Any) -> PublishResult:
    """执行单个发布任务，结果写回 job。"""
    channel = await db.get(am.CmsPublishChannel, job.channel_id)
    entry = await db.get(cms_models.Entry, job.entry_id)
    now = datetime.now(UTC)

    job.status = "running"
    job.started_at = now
    job.attempts = int(job.attempts or 0) + 1
    await db.commit()

    if channel is None:
        job.status = "failed"
        job.error = "渠道已被删除"
        job.finished_at = now
        await db.commit()
        return PublishResult(ok=False, error=job.error)

    if entry is None:
        job.status = "failed"
        job.error = "条目不存在或已删除"
        job.finished_at = now
        await db.commit()
        return PublishResult(ok=False, error=job.error)

    handler = CHANNELS.get(channel.channel_type)
    if handler is None:
        job.status = "failed"
        job.error = f"未知渠道类型：{channel.channel_type}"
        job.finished_at = now
        await db.commit()
        return PublishResult(ok=False, error=job.error)

    try:
        result = await handler.publish(db, entry, channel)
    except Exception as exc:
        log.warning("cms.publish.exception", job_id=job.id, error=str(exc))
        result = PublishResult(ok=False, error=f"{type(exc).__name__}: {exc}")

    job.finished_at = datetime.now(UTC)
    if result.ok:
        job.status = "skipped" if result.skipped else "success"
        job.external_id = result.external_id
        job.external_url = result.external_url
        job.error = None
    elif job.attempts < MAX_ATTEMPTS:
        # 还有重试机会就退回 pending，让下一轮 tick 再试
        job.status = "pending"
        job.error = (result.error or "")[:2000]
    else:
        job.status = "failed"
        job.error = (result.error or "")[:2000]
    if result.payload:
        job.payload = result.payload
    await db.commit()
    return result


async def run_pending(db: AsyncSession, *, limit: int = 10) -> dict[str, int]:
    """执行待处理任务。挂在 scheduler.tick 上，每轮跑几条。"""
    rows = (
        await db.execute(
            select(am.CmsPublishJob)
            .where(am.CmsPublishJob.status == "pending")
            .order_by(am.CmsPublishJob.id)
            .limit(limit)
        )
    ).scalars().all()
    if not rows:
        return {"ran": 0, "success": 0, "failed": 0, "retry": 0}

    stats = {"ran": 0, "success": 0, "failed": 0, "retry": 0}
    for job in rows:
        res = await run_job(db, job)
        stats["ran"] += 1
        if res.ok:
            stats["success"] += 1
        elif job.status == "pending":
            stats["retry"] += 1
        else:
            stats["failed"] += 1
    if stats["ran"]:
        log.info("cms.publish.batch", **stats)
    return stats


async def publish_entry(
    db: AsyncSession, entry_id: int, channel_keys: list[str] | None = None
) -> dict[str, Any]:
    """一步到位：建任务 + 立刻执行。返回每个渠道的结果，让前端能直接展示。"""
    entry = await db.get(cms_models.Entry, entry_id)
    if entry is None or getattr(entry, "deleted_at", None) is not None:
        raise ValueError("条目不存在")

    job_ids, missing = await enqueue(db, entry_id, channel_keys)

    # 渠道名写错的也放进结果里，让前端一眼看到「这个渠道名不认识」，
    # 而不是发完之后疑惑「怎么少了一个渠道」
    results: list[dict[str, Any]] = [
        {
            "channel": k,
            "channel_name": k,
            "ok": False,
            "skipped": False,
            "external_id": None,
            "external_url": None,
            "error": "渠道不存在，请检查渠道标识",
            "payload": {},
            "job_id": None,
            "status": "unknown_channel",
        }
        for k in missing
    ]

    if not job_ids:
        return {
            "entry_id": entry_id,
            "results": results,
            "note": "没有可用的渠道" if channel_keys else "没有启用的渠道，请先在渠道配置里开启",
        }

    jobs = (
        await db.execute(select(am.CmsPublishJob).where(am.CmsPublishJob.id.in_(job_ids)))
    ).scalars().all()

    for job in jobs:
        channel = await db.get(am.CmsPublishChannel, job.channel_id)
        res = await run_job(db, job)
        results.append(
            {
                "channel": channel.channel_key if channel else "?",
                "channel_name": channel.name if channel else "?",
                "ok": res.ok,
                "skipped": res.skipped,
                "external_id": res.external_id,
                "external_url": res.external_url,
                "error": res.error,
                "payload": res.payload,
                "job_id": job.id,
                "status": job.status,
            }
        )
    return {"entry_id": entry_id, "results": results}


async def job_stats(db: AsyncSession) -> dict[str, Any]:
    from sqlalchemy import func

    total = await db.scalar(select(func.count()).select_from(am.CmsPublishJob)) or 0
    rows = (
        await db.execute(
            select(am.CmsPublishJob.status, func.count()).group_by(am.CmsPublishJob.status)
        )
    ).all()
    return {"total": int(total), "by_status": {r[0]: int(r[1]) for r in rows}}


# ---------------------------------------------------------------------------
# 定时执行
# ---------------------------------------------------------------------------

_bg_tasks: set[Any] = set()


async def _drain_pending() -> None:
    from cenkor_admin.core.db import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await run_pending(db, limit=5)


from cenkor_admin.core.hooks import hook


@hook("scheduler.tick")
async def _hook_run_publish_jobs() -> None:
    """每轮调度捞几条发布任务执行。

    **必须**放到后台任务里跑，不能 await。scheduler 的 tick 同时负责定时
    发布和定时下线，而公众号接口最坏要等 15 秒 —— 一旦在 tick 里同步等
    接口返回，到点该发的内容会被一起拖住。宁可让它异步跑、晚一条任务，
    也不能让核心调度卡在别人的 API 上。
    """
    import asyncio

    try:
        task = asyncio.create_task(_drain_pending())
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
    except Exception as exc:
        log.warning("cms.publish.spawn_failed", error=str(exc))
