"""内容健康度体检。

## 为什么需要

CMS 里最容易腐烂的东西不是「没写完的草稿」，而是**上线之后就没人再看的内容**：
点了发布、图片挂了、SEO 没填、期限过了还挂着、正文薄得像摘要、
谁都不链它所以搜索引擎也当它不存在。

这些问题的共同点：**没有任何一个页面会报错**。它们只是默默拉低整站质量分，
而运营要发现问题，只能靠一条条点开看 —— 于是在条目过百之后，就再也没人看了。

所以：把「点开看」变成「一次算完，列个清单」。

## 十二项检查，三个维度

维度不是分类癖好：**结构问题改一条内容就能修，SEO 问题要动元数据或站点配置，
效果问题往往得改选题或改分发**。混在一张清单里，运营会先挑好改的改，
真正要命的问题永远排在后面。

### 结构维度（内容本身有没有硬伤）

| 检查 | 判定 | 严重度 |
|---|---|---|
| `expired` | `expire_at` 已过但仍是 published | critical |
| `dead_link` | 正文里指向站内条目的链接，目标不存在或未发布 | critical |
| `thin` | 正文纯文本字数低于阈值 | warning |
| `isolated` | 站内链接图谱里没有任何内容链到它 | warning |
| `no_image` | 正文无图且无 `seo.og_image` | warning |
| `stale` | 超过 N 天未更新 | warning |

### SEO 维度（搜索引擎能不能正确理解与收录）

| 检查 | 判定 | 严重度 |
|---|---|---|
| `no_slug` | 已发布但 slug 为空，生成不了公开页，也进不了 sitemap | critical |
| `seo_weak` | SEO 标题/描述缺失或长度越界、关键词为空 | warning |
| `cannibal` | 与另一篇抢同一主关键词（或关键词交集 ≥3） | warning |

### 效果维度（上线之后到底有没有用）

| 检查 | 判定 | 严重度 |
|---|---|---|
| `no_traffic` | 上线 ≥30 天，近 30 天零访问 | warning |
| `low_engagement` | 近 30 天 PV ≥30 且平均读完 <40% | warning |
| `no_conversion` | 近 30 天 PV ≥100 且零转化 | warning |

健康分 = 100 − 命中项扣分之和（下限 0），站点分 = 各条目分均值。
另给三个维度分（各自独立按 100 计），这样「结构 92 分但效果 40 分」
这种真相才看得见 —— 只有一个总分时，效果差会被结构分糊住。

### 效果维度为什么要一个开关

埋点刚接入时，所有条目都是「零访问」。这时候照直报，会得到一份
19 条全红的报告，谁看谁关掉。所以效果维度只在**统计表里已经有数据**
（`perf_ready`）时启用：先证明埋点在跑，再拿它评价内容。
埋点没接好时，报告会明说「效果维度未启用」，而不是假装每篇都死了。

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
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote, urlparse

from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# 正文抽取与 HTML 去标签复用 RAG 模块的实现，避免两套口径
# （体检说「正文 280 字」，RAG 切出来的也是同一份文本，对得上）
from cenkor_admin.apps.cms.ai.rag import _extract_body, _strip_html
from cenkor_admin.apps.cms.models import ContentType, Entry, SiteConfig
# 业务日口径与看板同源：用 UTC 切日会在北京时间早 8 点断一天
from cenkor_admin.apps.cms.tracking import biz_today

# ---------------------------------------------------------------------------
# 阈值与检查项定义
# ---------------------------------------------------------------------------

DEFAULT_STALE_DAYS = 365
DEFAULT_THIN_CHARS = 300

SEO_TITLE_MIN, SEO_TITLE_MAX = 10, 60
SEO_DESC_MIN, SEO_DESC_MAX = 50, 160

# --- 效果维度阈值 ---
# 窗长取 30 天：短于一周噪声太大（周一发的东西到周三还没被搜到），
# 长于 60 天又会把「改了标题之后变好」这件事糊掉。
PERF_WINDOW_DAYS = 30
# 新内容有爬虫收录延迟，30 天内零访问不算罪。百度/谷歌从提交到有量
# 常见 1~3 周，卡在 7 天会让人去改本来没问题的文章。
NO_TRAFFIC_MIN_AGE_DAYS = 30
# PV 太少时读完率没有统计意义（一次跳出就能把均值砸到 0）
LOW_ENGAGE_MIN_PV = 30
LOW_ENGAGE_SCROLL = 40
NO_CONV_MIN_PV = 100
# 关键词蚕食：主关键词完全相同，或关键词交集达到这个数
CANNIBAL_MIN_OVERLAP = 3

# 单次体检最多扫描的条目数（防止站点搬家式增长时把内存打爆）
_MAX_ENTRIES = 2000
# 单条正文参与内链解析的最大长度
_MAX_BODY_SCAN = 200_000

# dimension：structure / seo / performance —— 报告据此分组排序
CHECKS: dict[str, dict[str, Any]] = {
    "expired": {
        "label": "已过期仍在线上", "deduct": 30, "severity": "critical",
        "dimension": "structure",
    },
    "dead_link": {
        "label": "站内死链", "deduct": 20, "severity": "critical",
        "dimension": "structure",
    },
    "thin": {
        "label": "内容过薄", "deduct": 20, "severity": "warning",
        "dimension": "structure",
    },
    "isolated": {
        "label": "孤岛内容", "deduct": 10, "severity": "warning",
        "dimension": "structure",
    },
    "no_image": {
        "label": "缺配图", "deduct": 8, "severity": "warning",
        "dimension": "structure",
    },
    "stale": {
        "label": "长期未更新", "deduct": 8, "severity": "warning",
        "dimension": "structure",
    },
    "no_slug": {
        "label": "无法生成公开页", "deduct": 25, "severity": "critical",
        "dimension": "seo",
    },
    "seo_weak": {
        "label": "SEO 短板", "deduct": 15, "severity": "warning",
        "dimension": "seo",
    },
    "cannibal": {
        "label": "关键词自相竞争", "deduct": 8, "severity": "warning",
        "dimension": "seo",
    },
    "no_traffic": {
        "label": "零访问", "deduct": 6, "severity": "warning",
        "dimension": "performance",
    },
    "low_engagement": {
        "label": "读完率偏低", "deduct": 8, "severity": "warning",
        "dimension": "performance",
    },
    "no_conversion": {
        "label": "高流量零转化", "deduct": 5, "severity": "warning",
        "dimension": "performance",
    },
}

DIMENSIONS: dict[str, dict[str, str]] = {
    "structure": {"label": "结构", "hint": "内容本身有没有硬伤，改一篇就能修"},
    "seo": {"label": "SEO", "hint": "搜索引擎能不能正确理解与收录"},
    "performance": {"label": "效果", "hint": "上线之后到底有没有人看、看多久、有没有转化"},
}

# 修复建议：报告里每条问题后面跟一句「怎么改」。
# 不给建议的问题清单只是焦虑制造机 —— 运营看到 14 条红色，
# 第一反应不是去改，而是关掉页面。
REMEDIES: dict[str, str] = {
    "expired": "下线该内容，或把 expire_at 推到合理时间；若调度器没在跑，先查 scheduler",
    "dead_link": "修正或摘掉指向已删除/未发布内容的链接；确实需要指向的，先把目标发布",
    "thin": "补案例、补数据、补对比；写不出 300 字说明这个选题本来就不成立",
    "isolated": "从同主题的其他文章加一条内链指过来，或在列表页给出入口",
    "no_image": "给正文配一张图，或至少设 og_image —— 分享出去没封面点击率会掉一半",
    "stale": "更新数据与结论并改 updated_at；纯时间敏感内容考虑下线",
    "no_slug": "补一个语义化 slug（英文小写连字符）；slug 是公开页与 sitemap 的唯一凭据",
    "seo_weak": "按缺失项补：标题 10~60 字、描述 50~160 字、关键词 2~5 个",
    "cannibal": "两篇合并成一篇，或明确区分意图（一篇讲概念、一篇讲落地）并改用不同主关键词",
    "no_traffic": "先加内链把权重导过去；仍无流量说明选题没人搜，考虑改写标题或合并",
    "low_engagement": "开头 200 字直接给结论；把长段落拆开；检查是不是标题承诺了正文没给的东西",
    "no_conversion": "正文末尾加一个明确的下一步：下载清单、预约演示、看相关案例",
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
    perf: dict[str, Any] | None = None,
    cannibal: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """对单条条目做十二项检查，返回分数 + 问题清单。

    `perf` 为 None 表示效果维度未启用（埋点还没数据，或调用方不要求）；
    `cannibal` 为 None 表示没做关键词交叉分析。
    """
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

    # 8) 生成不了公开页
    #
    # slug 是公开页路径、sitemap 条目、JSON-LD 的 @id 三处的唯一凭据。
    # 为空时内容在后台显示「已发布」，但外部世界根本拿不到 URL ——
    # 这是最隐蔽的一种失效：不报错、不告警，只是没人来。
    slug = (entry.slug or "").strip()
    if entry.status == "published" and not slug:
        add("no_slug", "slug 为空：生成不了公开页，也进不了 sitemap，外部拿不到这个内容的 URL")

    # 9) 关键词自相竞争
    if cannibal:
        shared: list[str] = []
        for c in cannibal:
            for kw in c.get("shared") or []:
                if kw not in shared:
                    shared.append(kw)
        rivals = "、".join(f"#{c['entry_id']} {str(c.get('title') or '')[:18]}" for c in cannibal[:3])
        add(
            "cannibal",
            f"与 {len(cannibal)} 篇内容抢同一批关键词"
            f"（{('、'.join(shared[:3]) or '主关键词')}）：{rivals}",
            rivals=cannibal[:5],
            shared=shared,
        )

    # 10~12) 效果维度
    if perf is not None:
        pv = int(perf.get("pv") or 0)
        conv = int(perf.get("conversion") or 0)
        scroll = perf.get("scroll")
        age_days = _age_days(entry, now)

        if pv == 0 and age_days is not None and age_days >= NO_TRAFFIC_MIN_AGE_DAYS:
            add(
                "no_traffic",
                f"上线 {age_days} 天，近 {PERF_WINDOW_DAYS} 天没有任何访问",
                age_days=age_days,
            )
        if pv >= LOW_ENGAGE_MIN_PV and scroll is not None and scroll < LOW_ENGAGE_SCROLL:
            add(
                "low_engagement",
                f"近 {PERF_WINDOW_DAYS} 天 {pv} 次浏览，平均只读到 {scroll}%"
                f"（低于 {LOW_ENGAGE_SCROLL}%）",
                pv=pv,
                scroll=scroll,
            )
        if pv >= NO_CONV_MIN_PV and conv == 0:
            add(
                "no_conversion",
                f"近 {PERF_WINDOW_DAYS} 天 {pv} 次浏览、零转化（正文没有给出下一步）",
                pv=pv,
            )

    score = max(0, 100 - sum(i["deduct"] for i in issues))

    # 维度分：每个维度单独看 100 分底。
    # 不这样做的话，一篇「结构 100、效果 0」的内容总分会被平均成 88，
    # 看起来还行，实际问题在效果侧 —— 这正是最该被看见的一侧。
    dim_scores: dict[str, int] = {d: 100 for d in DIMENSIONS}
    for issue in issues:
        dim = CHECKS[issue["check"]]["dimension"]
        dim_scores[dim] = max(0, dim_scores[dim] - issue["deduct"])

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
        "dimensions": dim_scores,
        "issues": issues,
        "chars": len(text),
        "has_image": has_img,
        "inbound_links": inbound,
        "outbound_links": outbound,
        "updated_at": updated.isoformat() if updated else None,
        "performance": perf or None,
    }


def _age_days(entry: Entry, now: datetime) -> int | None:
    """上线天数。published_at 缺失时退回 created_at。"""
    ref = entry.published_at or entry.created_at
    if ref is None:
        return None
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return max(0, (now - ref).days)



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


async def _load_perf(session: AsyncSession) -> tuple[dict[int, dict[str, Any]], bool]:
    """一次取全站近 N 天效果，返回 (按 entry_id 的明细, 埋点是否就绪)。

    一次查完而不是逐条查：19 条时两者都行，2000 条时逐条查就是 2000 次往返。

    就绪判断用「统计表里有没有任何一行」而不是「近 N 天有没有」：
    埋点接好之后又挂掉，恰恰应该被报出来（全站零访问），
    用近 N 天判断会把这种事故静默掉。
    """
    today = biz_today()
    start = today - timedelta(days=max(1, PERF_WINDOW_DAYS) - 1)
    rows = (
        await session.execute(
            text(
                """
                SELECT entry_id,
                       SUM(pv)::int AS pv,
                       SUM(uv)::int AS uv,
                       ROUND(AVG(avg_scroll_pct))::int AS scroll,
                       ROUND(AVG(avg_duration_ms))::int AS dur,
                       SUM(conversion_count)::int AS conv
                  FROM cms_entry_stats_daily
                 WHERE stat_date BETWEEN :start AND :end
                   AND source = 'self'
                 GROUP BY entry_id
                """
            ),
            {"start": start, "end": today},
        )
    ).all()

    perf: dict[int, dict[str, Any]] = {
        r[0]: {
            "pv": r[1] or 0,
            "uv": r[2] or 0,
            "scroll": r[3],
            "duration": r[4],
            "conversion": r[5] or 0,
        }
        for r in rows
    }
    ready = bool(await session.scalar(text("SELECT EXISTS(SELECT 1 FROM cms_entry_stats_daily)")))
    return perf, ready


def _build_cannibal_index(entries: list[Entry]) -> dict[int, list[dict[str, Any]]]:
    """关键词自相竞争的倒排索引。

    判定：主关键词（seo.keywords 第一个）完全相同，或关键词交集 ≥ CANNIBAL_MIN_OVERLAP。

    为什么不用「交集 ≥2」：同一个主题写三篇（概念/落地/案例）本来就该共享
    两个词，报出来只会让人把系列文章合并掉，反而更糟。
    主关键词相同才是真的在抢同一个搜索位。

    一个词被超过 50 篇共用时不参与配对 —— 那是「分类词」不是「主关键词」，
    拿它判蚕食会让整个内容库互相判定为竞争对手。
    """
    kw_to_ids: dict[str, list[int]] = {}
    by_id: dict[int, Entry] = {}
    primary: dict[int, str] = {}

    for e in entries:
        seo = e.seo or {}
        raw = seo.get("keywords") or []
        if not isinstance(raw, list):
            continue
        kws = [str(k).strip().lower() for k in raw if str(k).strip()]
        if not kws:
            continue
        by_id[e.id] = e
        primary[e.id] = kws[0]
        for k in set(kws):
            kw_to_ids.setdefault(k, []).append(e.id)

    pairs: dict[tuple[int, int], set[str]] = {}
    for kw, ids in kw_to_ids.items():
        if len(ids) < 2 or len(ids) > 50:
            continue
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                key = (min(ids[i], ids[j]), max(ids[i], ids[j]))
                pairs.setdefault(key, set()).add(kw)

    out: dict[int, list[dict[str, Any]]] = {}
    for (a, b), shared in pairs.items():
        same_primary = primary.get(a) == primary.get(b)
        if not (same_primary or len(shared) >= CANNIBAL_MIN_OVERLAP):
            continue
        for me, other in ((a, b), (b, a)):
            out.setdefault(me, []).append(
                {
                    "entry_id": other,
                    "title": by_id[other].title,
                    "slug": by_id[other].slug,
                    "shared": sorted(shared),
                    "same_primary": same_primary,
                }
            )

    for k in out:
        out[k] = sorted(out[k], key=lambda x: (-len(x["shared"]), x["entry_id"]))[:5]
    return out



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

    perf, perf_ready = await _load_perf(session)
    cannibal = _build_cannibal_index(entries)

    scanned: list[dict[str, Any]] = []
    for e in entries:
        item = check_entry(
            e,
            graph,
            now=now,
            stale_days=stale_days,
            thin_chars=thin_chars,
            perf=perf.get(e.id, {}) if perf_ready else None,
            cannibal=cannibal.get(e.id),
        )
        ck = ct_key.get(e.content_type_id) or str(e.content_type_id)
        ident = e.slug or e.id
        item["content_type_key"] = ck
        item["public_url"] = f"/api/v1/public/site/{ck}/{ident}"
        scanned.append(item)

    total = len(scanned)
    avg = round(sum(i["score"] for i in scanned) / total, 1) if total else 100.0

    summary: dict[str, dict[str, Any]] = {
        c: {
            "label": meta["label"],
            "severity": meta["severity"],
            "dimension": meta["dimension"],
            "deduct": meta["deduct"],
            "remedy": REMEDIES.get(c, ""),
            "hit": 0,
        }
        for c, meta in CHECKS.items()
    }
    for item in scanned:
        for issue in item["issues"]:
            summary[issue["check"]]["hit"] += 1

    # 维度分：每个维度独立 100 分底，取该维度下所有条目分的均值。
    # 这样「结构 92、效果 41」这种分裂才看得出来 —— 只有一个总分时，
    # 效果差会被结构分糊住，而效果才是花钱做内容的人真正在意的。
    dimension_summary: dict[str, dict[str, Any]] = {}
    for d, meta in DIMENSIONS.items():
        vals = [i["dimensions"][d] for i in scanned]
        dimension_summary[d] = {
            "label": meta["label"],
            "hint": meta["hint"],
            "score": round(sum(vals) / len(vals), 1) if vals else 100.0,
            "enabled": d != "performance" or perf_ready,
            "checks": [
                {"check": c, "label": m["label"], "hit": summary[c]["hit"]}
                for c, m in CHECKS.items()
                if m["dimension"] == d
            ],
        }

    # 行动清单：按「命中数 × 单项扣分」排 —— 改一项能捞回多少分。
    # 报告里给的是「先改这 5 件」，不是一张 12 项的全量表。
    actions = sorted(
        (
            {
                "check": c,
                "label": m["label"],
                "dimension": m["dimension"],
                "severity": m["severity"],
                "hit": summary[c]["hit"],
                "impact": summary[c]["hit"] * m["deduct"],
                "remedy": REMEDIES.get(c, ""),
                "entries": [
                    {"entry_id": i["entry_id"], "title": i["title"]}
                    for i in scanned
                    if any(x["check"] == c for x in i["issues"])
                ][:8],
            }
            for c, m in CHECKS.items()
            if summary[c]["hit"] > 0
        ),
        key=lambda x: (-x["impact"], x["check"]),
    )

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
        f"problems={len(problem_entries)} level={level} perf_ready={perf_ready}"
    )

    return {
        "site_id": site_id,
        "generated_at": now.isoformat(),
        "scanned": total,
        "truncated": total >= _MAX_ENTRIES,
        "score": avg,
        "level": level,
        "check_summary": summary,
        "dimension_summary": dimension_summary,
        "actions": actions[:8],
        "perf_ready": perf_ready,
        "perf_window_days": PERF_WINDOW_DAYS,
        "problem_count": len(problem_entries),
        "entries": problem_entries[: max(1, min(limit, 500))],
        "thresholds": {
            "stale_days": stale_days,
            "thin_chars": thin_chars,
            "include_drafts": include_drafts,
            "seo_title": [SEO_TITLE_MIN, SEO_TITLE_MAX],
            "seo_description": [SEO_DESC_MIN, SEO_DESC_MAX],
            "no_traffic_min_age_days": NO_TRAFFIC_MIN_AGE_DAYS,
            "low_engagement": {"min_pv": LOW_ENGAGE_MIN_PV, "scroll_below": LOW_ENGAGE_SCROLL},
            "no_conversion": {"min_pv": NO_CONV_MIN_PV},
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

    perf, perf_ready = await _load_perf(session)
    cannibal = _build_cannibal_index(peers)

    item = check_entry(
        entry,
        graph,
        stale_days=stale_days,
        thin_chars=thin_chars,
        # perf_ready 但这条没有任何记录时传空 dict —— 那正是「确实零访问」，
        # 要让它报出来；传 None 是「整套效果维度没启用」，两者语义不同。
        perf=perf.get(entry.id, {}) if perf_ready else None,
        cannibal=cannibal.get(entry.id),
    )
    item["perf_ready"] = perf_ready
    ct_key = (
        await session.execute(select(ContentType.key).where(ContentType.id == entry.content_type_id))
    ).scalar_one_or_none() or str(entry.content_type_id)
    item["content_type_key"] = ct_key
    item["public_url"] = f"/api/v1/public/site/{ct_key}/{entry.slug or entry.id}"
    return item
