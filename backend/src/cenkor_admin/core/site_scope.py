"""CMS 多站点隔离：会话级自动过滤 + 写入自动打标。

## 为什么不用「每个查询手写 site_id」

管理端 + 公开端 + 内容引擎三个 router 共 96 处 `select()`。手写过滤有两个
躲不开的问题：漏一处就是跨站串数据，而且以后新写的查询默认又不带 —— 越加
越多，越难保证。所以把过滤下沉到 SQLAlchemy 会话层，一处实现覆盖全部。

## 实现要点

`do_orm_execute` 事件里给 statement 挂 `with_loader_criteria`，SQLAlchemy
会把它合并进 WHERE。实测覆盖三种写法（都验证过 count 与真实值一致）：

- `select(Entry)`          实体查询
- `select(Entry.id)`       纯列查询
- `select(func.count()).select_from(Entry)`   聚合 —— 分页 total 靠它

### criteria 必须用 literal，不能用闭包

第一版写成 `lambda cls: cls.site_id == sid`（sid 闭包捕获），结果 site=3
查出来的是 site=1 的数据：SQLAlchemy 把 lambda 编译结果缓存了，切换站点后
仍复用第一次的表达式。`track_closure_variables=False` 也救不了（实测仍
MISS）。`sa.literal(sid)` 让每个站点生成独立 SQL，缓存键随之不同，切站才
真正生效。站点数量有限，这点编译缓存开销可以接受。
（bindparam 方案直接报 `'LoaderCriteriaOption' object has no attribute
'__dict__'`，不可用。）

### 默认不过滤的取舍

contextvar 为 None 时不加条件 —— 脚本、CLI、定时任务、数据迁移保持原有
行为，不会因为「忘了设置站点」而查不到数据。HTTP 路径由中间件保证每个请求
都设置好，所以线上不会漏。这是有意的 fail-open：宁可脚本宽松，也不让后台
整片空白。

### 写入填充

`before_flush` 里给 `site_id is None` 的新对象补上当前站点。用 `is None`
判断而不是 `== 1`，所以显式指定 site_id=1 的场景不会被覆盖。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import sqlalchemy as sa
import structlog
from fastapi import HTTPException, Request
from sqlalchemy import event, select
from sqlalchemy.orm import Session, with_loader_criteria

log = structlog.get_logger(__name__)

# 当前请求的站点。None = 不做隔离（脚本场景）
_current_site_id: ContextVar[int | None] = ContextVar("cms_current_site_id", default=None)
# 豁免开关：站点管理、跨站统计等需要看全部数据
_bypass: ContextVar[bool] = ContextVar("cms_site_bypass", default=False)


class SiteScopeMissingError(RuntimeError):
    """strict 模式下查了带站点的表，却没有站点上下文。"""


# 兼容旧名：v0.5.27 之前叫 SiteScopeMissing，外部脚本可能还按旧名捕获。
SiteScopeMissing = SiteScopeMissingError


# fail-open / fail-closed 开关。默认 False 保持脚本与 CLI 的旧行为，
# HTTP 请求由中间件打开；后台任务用 site_scope_for() 打开。
_strict: ContextVar[bool] = ContextVar("cms_site_strict", default=False)

_SCOPED: tuple[type, ...] | None = None


def scoped_models() -> tuple[type, ...]:
    """内容归属表清单。延迟 import，避免与 models 形成循环依赖。"""
    global _SCOPED
    if _SCOPED is None:
        from cenkor_admin.apps.builder.models import Page
        from cenkor_admin.apps.cms.ab_models import AbTest
        from cenkor_admin.apps.cms.ai.models import (
            CmsAiAbRun,
            CmsAiBatchItem,
            CmsAiBatchJob,
            CmsAiEntryDigest,
            CmsAiGeneration,
            CmsAiMemory,
            CmsAiReview,
            CmsAiSession,
            CmsAiVideoJob,
        )
        from cenkor_admin.apps.cms.ai.workflow_models import CmsWorkflow, CmsWorkflowRun
        from cenkor_admin.apps.cms.analytics_models import (
            CmsEntryStatsDaily,
            CmsPublishChannel,
            CmsSearchLog,
            CmsTrackEvent,
        )
        from cenkor_admin.apps.cms.knowledge_models import KbDoc
        from cenkor_admin.apps.cms.seo_push_models import SeoPushJob
        from cenkor_admin.apps.cms.site_plan_models import SitePlan, SitePlanItem
        # monitor 是商业闭源模块（不进公开仓库）。公开包里没有它，
        # 这里必须降级成空元组，否则 scoped_models() 直接 ImportError。
        try:
            from cenkor_admin.apps.monitor.models import MonChannel, MonTarget
            _mon_models: tuple[type, ...] = (MonTarget, MonChannel)
        except (ImportError, ModuleNotFoundError):
            _mon_models = ()
        from cenkor_admin.apps.cms.models import (
            Case,
            Category,
            Entry,
            EntryLink,
            Media,
            News,
            Product,
            Tag,
        )
        from cenkor_admin.apps.cms.template_models import CmsTemplate
        from cenkor_admin.apps.forms.models import Form

        # 批次与批次条目也带 site_id：一个站点的批量生产不该被别的站点看到，
        # 更不该把草稿写进别的站点。
        _SCOPED = (
            # 内容归属
            Entry, EntryLink, Category, Tag, Media, Product, Case, News, Page, Form,
            # 批量生产与 AI 产物
            CmsAiBatchJob, CmsAiBatchItem, CmsAiGeneration, CmsAiReview,
            CmsAiAbRun, CmsAiVideoJob, CmsAiMemory, CmsAiEntryDigest, CmsAiSession,
            # 工作流 / 知识库 / 模板
            CmsWorkflow, CmsWorkflowRun, KbDoc, CmsTemplate,
            # 发布与统计
            CmsPublishChannel, CmsTrackEvent, CmsEntryStatsDaily, CmsSearchLog,
            # 建站方案 / 收录推送 / A/B
            SitePlan, SitePlanItem, SeoPushJob, AbTest,
            # 巡检（闭源模块，公开包中为空）
            *_mon_models,
        )
    return _SCOPED


# ---------------------------------------------------------------- 上下文读写


def current_site_id() -> int | None:
    """当前站点 id；None 表示未启用隔离。"""
    return _current_site_id.get()


def set_current_site(site_id: int | None) -> Any:
    return _current_site_id.set(site_id)


def reset_current_site(token: Any) -> None:
    _current_site_id.reset(token)


@contextmanager
def site_scope_for(site_id: int | None) -> Iterator[None]:
    """后台任务/定时任务入口：设站点上下文，并开启 strict。"""
    sid_token = _current_site_id.set(site_id)
    strict_token = _strict.set(site_id is not None)
    try:
        yield
    finally:
        _strict.reset(strict_token)
        _current_site_id.reset(sid_token)


@contextmanager
def site_scope_strict(enabled: bool = True) -> Iterator[None]:
    """只切 fail-closed 开关，不动当前站点（临时演练用）。"""
    token = _strict.set(enabled)
    try:
        yield
    finally:
        _strict.reset(token)


@contextmanager
def site_scope_bypass() -> Iterator[None]:
    """临时关闭站点过滤（站点管理 API、跨站统计）。"""
    token = _bypass.set(True)
    try:
        yield
    finally:
        _bypass.reset(token)


def require_site_id() -> int:
    """取当前站点，取不到直接报错 —— 用于必须有站点上下文的端点。"""
    sid = _current_site_id.get()
    if sid is None:
        raise HTTPException(status_code=400, detail="无法确定站点上下文，请指定 X-Site-Id")
    return sid


# ---------------------------------------------------------------- SQLAlchemy 事件


def _install_events() -> None:
    @event.listens_for(Session, "do_orm_execute")
    def _apply_site_filter(execute_state: Any) -> None:
        if _bypass.get():
            return
        sid = _current_site_id.get()
        if sid is None:
            # 旧行为：静默放行（脚本/迁移）。strict 下改成直接报错，
            # 否则后台任务会把 A 站的数据当成 B 站的。
            if _strict.get():
                raise SiteScopeMissingError(
                    "站点上下文缺失：本次查询命中带 site_id 的表，但没有当前站点。"
                    "后台任务入口请用 site_scope_for(site_id) 包一层；"
                    "确需跨站请显式 with site_scope_bypass()。"
                )
            return
        if not execute_state.is_select:
            return
        # 懒加载不算：父对象已按站点过滤过，子对象跟着父对象走，
        # 重复加条件会让「关联到别的站点的条目」静默变空。
        if execute_state.is_column_load or execute_state.is_relationship_load:
            return

        execute_state.statement = execute_state.statement.options(
            *[
                with_loader_criteria(m, m.site_id == sa.literal(sid), include_aliases=True)
                for m in scoped_models()
            ]
        )

    @event.listens_for(Session, "before_flush")
    def _stamp_site_id(session: Session, flush_context: Any, instances: Any) -> None:
        if _bypass.get():
            return
        sid = _current_site_id.get()
        if sid is None:
            # 不拦的话会写出 site_id=NULL 的行，之后任何站点都查不到，
            # 变成「看得见写入、看不见数据」的幽灵记录。
            if _strict.get() and any(
                isinstance(o, scoped_models()) and getattr(o, "site_id", None) is None
                for o in session.new
            ):
                raise SiteScopeMissingError(
                    "写入被拦：对象缺 site_id 且没有当前站点。"
                    "请用 site_scope_for(site_id) 包住写入逻辑。"
                )
            return
        models = scoped_models()
        for obj in session.new:
            if isinstance(obj, models) and getattr(obj, "site_id", None) is None:
                obj.site_id = sid


_install_events()


# ---------------------------------------------------------------- 站点解析


class _SiteCache:
    """host → site_id 映射 + 有效站点集合，30 秒 TTL。

    中间件每个请求都要跑，不能每次都查库；站点是低频变更数据，
    30 秒的过期窗口对运营完全无感。

    过期瞬间会有很多请求同时发现缓存失效，用锁 + 双重检查只让一个去查库，
    其余等它填好直接复用 —— 否则高峰期过期一次就是一波连接抢占。
    """

    TTL = 30.0

    def __init__(self) -> None:
        self.at: float = 0.0
        self.hosts: dict[str, int] = {}
        self.ids: set[int] = set()
        self.default: int | None = None
        self.loaded: bool = False
        self._lock = asyncio.Lock()

    def _fresh(self) -> bool:
        return self.loaded and (time.monotonic() - self.at) < self.TTL

    async def load(self) -> _SiteCache:
        if self._fresh():
            return self
        async with self._lock:
            if self._fresh():  # 等锁期间可能已被别人填好
                return self
            return await self._reload()

    async def _reload(self) -> _SiteCache:
        from cenkor_admin.apps.cms.models import Site
        from cenkor_admin.core.db import AsyncSessionLocal

        try:
            async with AsyncSessionLocal() as db:
                rows = (
                    await db.execute(
                        select(Site.id, Site.domain, Site.status)
                        .where(Site.status == "active")
                        .order_by(Site.sort, Site.id)
                    )
                ).all()
        except Exception as exc:
            # 查不到就沿用上次结果，别让中间件把整个后台拖挂
            log.warning("cms.site.cache_load_failed", error=str(exc))
            return self

        self.hosts = {
            r.domain.lower().strip(): r.id for r in rows if r.domain and r.domain.strip()
        }
        self.ids = {r.id for r in rows}
        # 默认站 = sort 最小、id 最小的活跃站点
        self.default = rows[0].id if rows else None
        self.at = time.monotonic()
        self.loaded = True
        return self


_cache = _SiteCache()


def _parse_explicit(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def site_scope_middleware(request: Request, call_next: Any) -> Any:
    """把当前站点写进 contextvar，供 ORM 事件与端点读取。

    优先级：X-Site-Id 头 > ?site_id= > 请求域名 > 默认站点。
    显式指定必须是活跃站点，非法值直接忽略（不报错，回落到默认），
    因为中间件报错等于整站 500，代价远大于「切站没生效」。
    """
    cache = await _cache.load()

    sid: int | None = None
    source = "none"

    explicit = _parse_explicit(
        request.headers.get("x-site-id") or request.query_params.get("site_id")
    )
    if explicit is not None and explicit in cache.ids:
        sid, source = explicit, "explicit"

    if sid is None:
        host = (request.headers.get("host") or "").split(":")[0].strip().lower()
        if host and host in cache.hosts:
            sid, source = cache.hosts[host], "host"

    if sid is None and cache.default is not None:
        sid, source = cache.default, "default"

    token = _current_site_id.set(sid)
    strict_token = _strict.set(True)
    try:
        request.state.site_id = sid
        request.state.site_source = source
        return await call_next(request)
    finally:
        _strict.reset(strict_token)
        _current_site_id.reset(token)


async def invalidate_site_cache() -> None:
    """站点被增删改后调用，让下一个请求重新加载。"""
    _cache.at = 0.0
    _cache.loaded = False
