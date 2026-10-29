"""内容健康度体检。

## 为什么需要

CMS 里最容易腐烂的东西不是「没写完的草稿」，而是**上线之后就没人再看的内容**：
点了发布、图片挂了、SEO 没填、期限过了还挂着、正文薄得像摘要、
谁都不链它所以搜索引擎也当它不存在。

这些问题的共同点：**没有任何一个页面会报错**。它们只是默默拉低整站质量分，
而运营要发现问题，只能靠一条条点开看 —— 于是在条目过百之后，就再也没人看了。

所以：把「点开看」变成「一次算完，列个清单」。

## 七项检查

| 检查 | 判定 | 严重度 |
|---|---|---|
| `expired` | `expire_at` 已过但仍是 published | critical |
| `dead_link` | 正文里指向站内条目的链接，目标不存在或未发布 | critical |
| `thin` | 正文纯文本字数低于阈值 | warning |
| `seo_weak` | SEO 标题/描述缺失或长度越界、关键词为空 | warning |
| `isolated` | 站内链接图谱里没有任何内容链到它 | warning |
| `no_image` | 正文无图且无 `seo.og_image` | warning |
| `stale` | 超过 N 天未更新 | warning |

健康分 = 100 − 命中项扣分之和（下限 0），站点分 = 各条目分均值。

## 内链图谱的诚实边界

判定站内链接需要知道「哪些形态算站内」。这里的做法：
1. **explicit**：`/site/{key}/{ident}` 形态（含 `/api/v1/public/site/...`）——
   这是本系统自己的产出形态，可以精确校验目标是否存在，因此能判死链
2. **heuristic**：相对路径 `/xxx`、以及绝对 URL 且 host 属于站点域名
   （取自 `cms_site_config` 的 `brand.domain`）—— 只用于统计链入/链出，**不判死链**
3. 其余（外站、`#`、`mailto:`、`tel:`、`javascript:`）一律跳过

为什么 2 不判死链：官网站点的路由形态不在 CMS 管辖范围（www 是独立应用），
拿 CMS 的 slug 去校验它的路径只会制造误报。**宁可漏报，不要误报** ——
一个天天喊狼来了的体检报告，第二次就没人看了。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote, urlparse

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# 正文抽取与 HTML 去标签复用 RAG 模块的实现，避免两套口径
# （体检说「正文 280 字」，RAG 切出来的也是同一份文本，对得上）
from cenkor_admin.apps.cms.ai.rag import _extract_body, _strip_html
from cenkor_admin.apps.cms.models import ContentType, Entry, SiteConfig

# ---------------------------------------------------------------------------
# 阈值与检查项定义
# ---------------------------------------------------------------------------

DEFAULT_STALE_DAYS = 365
DEFAULT_THIN_CHARS = 300

SEO_TITLE_MIN, SEO_TITLE_MAX = 10, 60
SEO_DESC_MIN, SEO_DESC_MAX = 50, 160

# 单次体检最多扫描的条目数（防止站点搬家式增长时把内存打爆）
_MAX_ENTRIES = 2000
# 单条正文参与内链解析的最大长度
_MAX_BODY_SCAN = 200_000

CHECKS: dict[str, dict[str, Any]] = {
    "expired": {"label": "已过期仍在线上", "deduct": 30, "severity": "critical"},
    "dead_link": {"label": "站内死链", "deduct": 20, "severity": "critical"},
    "thin": {"label": "内容过薄", "deduct": 20, "severity": "warning"},
    "seo_weak": {"label": "SEO 短板", "deduct": 15, "severity": "warning"},
    "isolated": {"label": "孤岛内容", "deduct": 10, "severity": "warning"},
    "no_image": {"label": "缺配图", "deduct": 8, "severity": "warning"},
    "stale": {"label": "长期未更新", "deduct": 8, "severity": "warning"},
}

_LEVEL_ORDER = {"critical": 0, "warning": 1, "healthy": 2}

_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']{1,2000})["']""", re.IGNORECASE)
_IMG_RE = re.compile(r"<img\b", re.IGNORECASE)
_EXPLICIT_SITE_RE = re.compile(r"/site/([^/\s\"'?#]+)/([^/\s\"'?#]+)", re.IGNORECASE)
_SKIP_PREFIXES = ("#", "mailto:", "tel:", "javascript:", "data:")


# ---------------------------------------------------------------------------
# 链接解析
# ---------------------------------------------------------------------------


def _extract_hrefs(body: str) -> list[str]:
    if not body:
        return []
    return _HREF_RE.findall(body[:_MAX_BODY_SCAN])


def _resolve_href(href: str, domain: str) -> tuple[str, bool]:
    """解析一个 href → (ident, explicit)。

    ident 为空表示「不是可判定的站内链接」，调用方直接忽略。
    explicit=True 表示这是 `/site/{key}/{ident}` 形态，可以判死链。
    """
    raw = (href or "").strip()
    if not raw or raw.lower().startswith(_SKIP_PREFIXES):
        return "", False

    m = _EXPLICIT_SITE_RE.search(raw)
    if m:
        return unquote(m.group(2)).strip(), True

    if raw.startswith("//"):
        return "", False

    if raw.lower().startswith(("http://", "https://")):
        try:
            host = (urlparse(raw).hostname or "").lower()
        except ValueError:
            return "", False
        d = (domain or "").lower().lstrip(".")
        if not d or not (host == d or host.endswith("." + d)):
            return "", False
        path = urlparse(raw).path or ""
    elif raw.startswith("/"):
        path = raw
    else:
        # 相对路径（如 "news/abc"）也当站内，但不判死链
        path = raw if "/" in raw else ""
        if not path:
            return "", False

    seg = path.split("#")[0].split("?")[0].rstrip("/").split("/")[-1]
    return unquote(seg).strip(), False


class _LinkGraph:
    """站内链接图谱：入度 / 出度 / 死链。"""

    def __init__(self) -> None:
        self.inbound: dict[int, int] = {}
        self.outbound: dict[int, int] = {}
        self.dead: dict[int, list[str]] = {}

    def inbound_of(self, entry_id: int) -> int:
        return self.inbound.get(entry_id, 0)

    def outbound_of(self, entry_id: int) -> int:
        return self.outbound.get(entry_id, 0)

    def dead_of(self, entry_id: int) -> list[str]:
        return self.dead.get(entry_id, [])


def _build_graph(entries: list[Entry], domain: str) -> _LinkGraph:
    by_id = {e.id: e for e in entries}
    by_slug = {(e.slug or "").strip().lower(): e.id for e in entries if (e.slug or "").strip()}
    graph = _LinkGraph()

    for e in entries:
        body = _extract_body(e.content or {})
        seen_targets: set[int] = set()
        for href in _extract_hrefs(body):
            ident, explicit = _resolve_href(href, domain)
            if not ident:
                continue
            target: int | None = None
            if ident.isdigit():
                tid = int(ident)
                target = tid if tid in by_id else None
            else:
                target = by_slug.get(ident.lower())

            if target is None:
                # 只有 explicit 形态才判死链：heuristic 形态可能对应官网站点路由
                if explicit:
                    graph.dead.setdefault(e.id, []).append(href[:200])
                continue
            if target == e.id:
                continue  # 自链不计
            graph.inbound[target] = graph.inbound.get(target, 0) + 1
            seen_targets.add(target)

        if seen_targets:
            graph.outbound[e.id] = len(seen_targets)

    return graph


# ---------------------------------------------------------------------------
# 单条体检
# ---------------------------------------------------------------------------


def _seo_problems(seo: dict[str, Any] | None) -> list[str]:
    seo = seo or {}
    problems: list[str] = []

    title = str(seo.get("title") or "").strip()
    if not title:
        problems.append("缺 SEO 标题")
    elif len(title) < SEO_TITLE_MIN:
        problems.append(f"SEO 标题过短（{len(title)} 字）")
    elif len(title) > SEO_TITLE_MAX:
        problems.append(f"SEO 标题过长（{len(title)} 字，会被截断）")

    desc = str(seo.get("description") or "").strip()
    if not desc:
        problems.append("缺 meta 描述")
    elif len(desc) < SEO_DESC_MIN:
        problems.append(f"meta 描述过短（{len(desc)} 字，建议 {SEO_DESC_MIN}+）")
    elif len(desc) > SEO_DESC_MAX:
        problems.append(f"meta 描述过长（{len(desc)} 字）")

    kws = seo.get("keywords") or []
    if not isinstance(kws, list) or not [k for k in kws if str(k).strip()]:
        problems.append("缺关键词")

    return problems


def check_entry(
    entry: Entry,
    graph: _LinkGraph,
    *,
    now: datetime | None = None,
    stale_days: int = DEFAULT_STALE_DAYS,
    thin_chars: int = DEFAULT_THIN_CHARS,
) -> dict[str, Any]:
    """对单条条目做七项检查，返回分数 + 问题清单。"""
    now = now or datetime.now(timezone.utc)
    body = _extract_body(entry.content or {})
    text = _strip_html(body)
    seo = entry.seo or {}
    issues: list[dict[str, Any]] = []

    def add(check: str, message: str, **extra: Any) -> None:
        meta = CHECKS[check]
        issues.append(
            {
                "check": check,
                "label": meta["label"],
                "severity": meta["severity"],
                "deduct": meta["deduct"],
                "message": message,
                **extra,
            }
        )

    # 1) 过期仍在线
    #
    # 注意语义：`core/scheduler.py` 每 30s 会把到期的已发布条目自动下线为
    # archived，所以正常运转下这个检查**几乎不会命中**。它真正的价值是
    # 「调度器健康度探针」—— 一旦命中，说明 scheduler 没跑或失效了。
    if entry.status == "published" and entry.expire_at is not None:
        expire_at = entry.expire_at
        if expire_at.tzinfo is None:
            expire_at = expire_at.replace(tzinfo=timezone.utc)
        if expire_at <= now:
            add(
                "expired",
                f"已于 {expire_at:%Y-%m-%d} 过期，但仍处于已发布状态（调度器可能未运行）",
                expire_at=expire_at.isoformat(),
            )

    # 2) 站内死链
    dead = graph.dead_of(entry.id)
    if dead:
        add("dead_link", f"正文有 {len(dead)} 个站内链接指向不存在或未发布的内容", hrefs=dead[:5])

    # 3) 内容过薄
    if len(text) < thin_chars:
        add("thin", f"正文仅 {len(text)} 字（建议 {thin_chars}+）", chars=len(text))

    # 4) SEO 短板
    seo_problems = _seo_problems(seo)
    if seo_problems:
        add("seo_weak", "；".join(seo_problems), problems=seo_problems)

    # 5) 孤岛 / 孤儿
    inbound = graph.inbound_of(entry.id)
    outbound = graph.outbound_of(entry.id)
    if inbound == 0 and outbound == 0:
        add("isolated", "没有任何站内链接进或出（孤岛内容）", inbound=0, outbound=0)
    elif inbound == 0:
        add("isolated", "没有任何内容链接到它（孤儿页）", inbound=0, outbound=outbound)

    # 6) 缺配图
    has_img = bool(_IMG_RE.search(body or "")) or bool(str(seo.get("og_image") or "").strip())
    if not has_img:
        add("no_image", "正文无图且未设 og_image")

    # 7) 长期未更新
    updated = entry.updated_at
    if updated is not None:
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        days = (now - updated).days
        if days > stale_days:
            add("stale", f"已 {days} 天未更新", days=days)

    score = max(0, 100 - sum(i["deduct"] for i in issues))
    has_critical = any(i["severity"] == "critical" for i in issues)
    level = "critical" if (has_critical or score < 60) else "warning" if score < 85 else "healthy"

    return {
        "entry_id": entry.id,
        "title": entry.title,
        "slug": entry.slug,
        "status": entry.status,
        "content_type_id": entry.content_type_id,
        "score": score,
        "level": level,
        "issues": issues,
        "chars": len(text),
        "has_image": has_img,
        "inbound_links": inbound,
        "outbound_links": outbound,
        "updated_at": updated.isoformat() if updated else None,
    }


# ---------------------------------------------------------------------------
# 站点体检
# ---------------------------------------------------------------------------


async def _site_domain(session: AsyncSession) -> str:
    row = (
        await session.execute(select(SiteConfig.value).where(SiteConfig.key == "brand.domain"))
    ).scalar_one_or_none()
    if isinstance(row, str):
        return row.strip()
    return ""


async def site_health(
    session: AsyncSession,
    site_id: int,
    *,
    include_drafts: bool = False,
    limit: int = 200,
    stale_days: int = DEFAULT_STALE_DAYS,
    thin_chars: int = DEFAULT_THIN_CHARS,
) -> dict[str, Any]:
    """全站体检：算出每条的健康分，再汇总。

    `limit` 只限制**问题条目明细**的返回条数，扫描范围仍是全站
    （否则分数会随分页漂移，同一个站点两次刷新分数不一样 = 报告不可信）。
    """
    now = datetime.now(timezone.utc)

    stmt = select(Entry).where(Entry.site_id == site_id, Entry.deleted_at.is_(None))
    if not include_drafts:
        stmt = stmt.where(Entry.status == "published")
    stmt = stmt.order_by(Entry.id.desc()).limit(_MAX_ENTRIES)
    entries = list((await session.execute(stmt)).scalars().all())

    domain = await _site_domain(session)
    graph = _build_graph(entries, domain)

    ct_rows = (
        await session.execute(select(ContentType.id, ContentType.key))
    ).all()
    ct_key = {r[0]: r[1] for r in ct_rows}

    scanned: list[dict[str, Any]] = []
    for e in entries:
        item = check_entry(e, graph, now=now, stale_days=stale_days, thin_chars=thin_chars)
        ck = ct_key.get(e.content_type_id) or str(e.content_type_id)
        ident = e.slug or e.id
        item["content_type_key"] = ck
        item["public_url"] = f"/api/v1/public/site/{ck}/{ident}"
        scanned.append(item)

    total = len(scanned)
    avg = round(sum(i["score"] for i in scanned) / total, 1) if total else 100.0

    summary: dict[str, dict[str, Any]] = {
        c: {"label": meta["label"], "severity": meta["severity"], "hit": 0} for c, meta in CHECKS.items()
    }
    for item in scanned:
        for issue in item["issues"]:
            summary[issue["check"]]["hit"] += 1

    problem_entries = sorted(
        (i for i in scanned if i["issues"]),
        key=lambda x: (x["score"], _LEVEL_ORDER.get(x["level"], 9)),
    )
    level = (
        "critical"
        if any(i["level"] == "critical" for i in scanned) or avg < 60
        else "warning"
        if avg < 85
        else "healthy"
    )

    logger.info(
        f"[content_health] site={site_id} scanned={total} avg={avg} "
        f"problems={len(problem_entries)} level={level}"
    )

    return {
        "site_id": site_id,
        "generated_at": now.isoformat(),
        "scanned": total,
        "truncated": total >= _MAX_ENTRIES,
        "score": avg,
        "level": level,
        "check_summary": summary,
        "problem_count": len(problem_entries),
        "entries": problem_entries[: max(1, min(limit, 500))],
        "thresholds": {
            "stale_days": stale_days,
            "thin_chars": thin_chars,
            "include_drafts": include_drafts,
            "seo_title": [SEO_TITLE_MIN, SEO_TITLE_MAX],
            "seo_description": [SEO_DESC_MIN, SEO_DESC_MAX],
        },
    }


async def entry_health(
    session: AsyncSession,
    entry_id: int,
    *,
    stale_days: int = DEFAULT_STALE_DAYS,
    thin_chars: int = DEFAULT_THIN_CHARS,
) -> dict[str, Any] | None:
    """单条体检。图谱取同站点全量已发布条目，保证入度统计准确。"""
    entry = (
        await session.execute(
            select(Entry).where(Entry.id == entry_id, Entry.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if entry is None:
        return None

    peers = list(
        (
            await session.execute(
                select(Entry)
                .where(
                    Entry.site_id == entry.site_id,
                    Entry.deleted_at.is_(None),
                    Entry.status == "published",
                )
                .limit(_MAX_ENTRIES)
            )
        )
        .scalars()
        .all()
    )
    domain = await _site_domain(session)
    graph = _build_graph(peers, domain)

    item = check_entry(entry, graph, stale_days=stale_days, thin_chars=thin_chars)
    ct_key = (
        await session.execute(select(ContentType.key).where(ContentType.id == entry.content_type_id))
    ).scalar_one_or_none() or str(entry.content_type_id)
    item["content_type_key"] = ct_key
    item["public_url"] = f"/api/v1/public/site/{ct_key}/{entry.slug or entry.id}"
    return item
