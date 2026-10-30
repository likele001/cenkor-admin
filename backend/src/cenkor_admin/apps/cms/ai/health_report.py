"""整站 SEO 体检报告：把 `site_health()` 的结果渲染成可交付文档。

## 为什么单独一个模块

`content_health.py` 负责**算**，这里负责**说**。混在一起的话，
改一次报告措辞就要动体检逻辑，改一次阈值又要回头看输出格式。

## 报告和面板的区别

面板是给自己天天看的：密度高、可筛选、能点进去。
报告是发给别人的：客户、老板、外包写手。

所以报告必须自己把话说清楚 —— 谁是站点、什么时候扫的、扫了多少篇、
什么算「过薄」、为什么这条算问题、该怎么改。
一份对方看不懂口径的报告，结论再对也会被当成「工具瞎报」。

## 两处诚实边界（报告里明写，不藏）

1. **没做的检查**：外链质量、Core Web Vitals、移动端渲染、收录量。
   这些要么需要外部数据源，要么需要真实浏览器跑分，CMS 里拿不到。
   假装做了比不做更糟 —— 客户拿去对着 Search Console 一比就露馅。
2. **内链的 heuristic 部分不判死链**：官网站点路由不在 CMS 管辖范围，
   拿 CMS 的 slug 去校验它的路径只会制造误报。
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from cenkor_admin.apps.cms.ai.content_health import (
    CHECKS,
    DIMENSIONS,
    LOW_ENGAGE_MIN_PV,
    LOW_ENGAGE_SCROLL,
    NO_CONV_MIN_PV,
    NO_TRAFFIC_MIN_AGE_DAYS,
    PERF_WINDOW_DAYS,
    SEO_DESC_MAX,
    SEO_DESC_MIN,
    SEO_TITLE_MAX,
    SEO_TITLE_MIN,
)

_TZ = ZoneInfo("Asia/Shanghai")

LEVEL_LABEL = {"critical": "需要处理", "warning": "有待改进", "healthy": "健康"}
SEVERITY_LABEL = {"critical": "严重", "warning": "一般"}

# 等级阈值必须和 `content_health.check_entry` 里的 level 判定**完全一致**，
# 否则报告头部写「健康」、结论段写「有明显短板」，同一份报告自相矛盾。
# 那边是：<60 critical，<85 warning，其余 healthy。
_LEVEL_CUTS = [(85, "healthy"), (60, "warning"), (0, "critical")]

# 分数区间 → 一句话结论。报告开头先给判断，再给数据。
_VERDICT = [
    (85, "整体健康", "结构和元数据没有硬伤。按下方清单做增量优化即可，不必专门排期治理。"),
    (70, "有待改进", "存在一批影响收录或点击的问题，建议排一次集中处理，别零散地改。"),
    (60, "问题较多", "多个维度同时失守，零散修改效果有限，建议立项做专项。"),
    (0, "需要立即处理", "存在会让内容无法被正常收录或访问的严重问题，先处理清单前几项。"),
]


def _verdict(score: float) -> tuple[str, str]:
    for floor, title, desc in _VERDICT:
        if score >= floor:
            return title, desc
    return "需要立即处理", ""


def _e(value: Any) -> str:
    """HTML 转义。报告里所有来自内容库的文本都必须过这一层。"""
    return html.escape(str(value if value is not None else ""), quote=True)


def _local_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(_TZ).strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return iso or ""


def _score_level(score: float) -> str:
    for floor, name in _LEVEL_CUTS:
        if score >= floor:
            return name
    return "critical"


# 等级名（healthy/warning/critical）和 CSS 类名（ok/warn/bad）是两套词表。
# 不映射的话样式全部落空：数字该绿的不绿、进度条永远是一条灰线。
_CSS_CLASS = {"healthy": "ok", "warning": "warn", "critical": "bad"}


def _cls(score: float) -> str:
    return _CSS_CLASS[_score_level(score)]


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def render_markdown(report: dict[str, Any], *, site_name: str = "") -> str:
    """Markdown 版：贴进文档、飞书、Confluence 都不变形。"""
    score = float(report.get("score") or 0)
    verdict, verdict_desc = _verdict(score)
    level = LEVEL_LABEL.get(report.get("level") or "", "")
    dims: dict[str, Any] = report.get("dimension_summary") or {}
    actions: list[dict[str, Any]] = report.get("actions") or []
    summary: dict[str, Any] = report.get("check_summary") or {}
    entries: list[dict[str, Any]] = report.get("entries") or []

    th: dict[str, Any] = report.get("thresholds") or {}
    scanned = int(report.get("scanned") or 0)
    scope = "内容（含草稿）" if th.get("include_drafts") else "已发布内容"

    out: list[str] = []
    out.append(f"# 整站内容与 SEO 体检报告{'：' + site_name if site_name else ''}")
    out.append("")
    out.append(f"- 生成时间：{_local_time(report.get('generated_at') or '')}")
    scope_line = f"- 扫描范围：{scanned} 篇{scope}"
    if report.get("truncated"):
        scope_line += "（已达扫描上限 2000 篇，站内内容更多，分数只代表被扫到的部分）"
    out.append(scope_line)
    out.append("- 判定口径：结构 + SEO + 效果三个维度，各 100 分底")
    out.append("")
    out.append("## 一、结论")
    out.append("")
    out.append(f"**综合得分 {score:.1f} / 100 —— {level}**")
    out.append("")
    out.append(f"{verdict}。{verdict_desc}")
    out.append("")

    if dims:
        out.append("| 维度 | 分数 | 状态 | 说明 |")
        out.append("|---|---|---|---|")
        for d in ("structure", "seo", "performance"):
            info = dims.get(d) or {}
            if not info:
                continue
            enabled = info.get("enabled", True)
            ds = float(info.get("score") or 0)
            out.append(
                f"| {info.get('label') or d} | "
                f"{'—' if not enabled else f'{ds:.1f}'} | "
                f"{'未启用' if not enabled else LEVEL_LABEL.get(_score_level(ds), '')} | "
                f"{info.get('hint') or ''} |"
            )
        out.append("")

    if not report.get("perf_ready"):
        out.append(
            "> 效果维度未启用：埋点还没有采集到任何数据。接入埋点后，"
            "这里会给出零访问、读完率、转化三类问题。"
        )
        out.append("")

    out.append("## 二、先改这几件")
    out.append("")
    if actions:
        out.append("按「命中篇数 × 单条扣分」排序 —— 先改影响面最大的。")
        out.append("")
        for idx, a in enumerate(actions[:8], 1):
            out.append(
                f"{idx}. **{a.get('label')}** — {a.get('hit')} 篇，"
                f"影响面 {a.get('impact')}（{SEVERITY_LABEL.get(a.get('severity'), '')}）"
            )
            if a.get("remedy"):
                out.append(f"   - 怎么改：{a['remedy']}")
            names = [f"{x.get('title')}" for x in (a.get("entries") or [])[:4]]
            if names:
                more = len(a.get("entries") or []) - len(names)
                tail = f" 等 {len(a.get('entries') or [])} 篇" if more > 0 else ""
                out.append(f"   - 涉及：{'；'.join(names)}{tail}")
        out.append("")
    else:
        out.append("没有需要处理的问题。")
        out.append("")

    out.append("## 三、问题分布")
    out.append("")
    out.append("| 维度 | 检查项 | 严重度 | 命中 | 单条扣分 | 影响面 |")
    out.append("|---|---|---|---|---|---|")
    any_hit = False
    for dim_key in ("structure", "seo", "performance"):
        for ck, meta in CHECKS.items():
            if meta["dimension"] != dim_key:
                continue
            row = summary.get(ck) or {}
            hit = int(row.get("hit") or 0)
            if hit == 0:
                continue
            any_hit = True
            out.append(
                f"| {DIMENSIONS[dim_key]['label']} | {meta['label']} | "
                f"{SEVERITY_LABEL.get(meta['severity'], '')} | {hit} | "
                f"{meta['deduct']} | {hit * meta['deduct']} |"
            )
    if not any_hit:
        out.append("| — | 无命中项 | — | 0 | — | 0 |")
    out.append("")

    out.append("## 四、问题明细")
    out.append("")
    if entries:
        out.append("| 分数 | 标题 | 结构 | SEO | 效果 | 问题 |")
        out.append("|---|---|---|---|---|---|")
        for item in entries[:50]:
            dm = item.get("dimensions") or {}
            issues = "；".join(i.get("label") or "" for i in (item.get("issues") or []))
            out.append(
                f"| {item.get('score')} | {item.get('title') or ''} | "
                f"{dm.get('structure', '—')} | {dm.get('seo', '—')} | "
                f"{dm.get('performance', '—')} | {issues} |"
            )
        if len(entries) > 50:
            out.append("")
            out.append(f"（仅列出前 50 篇，共 {len(entries)} 篇有问题）")
        out.append("")
    else:
        out.append("没有有问题的内容。")
        out.append("")

    out.append("## 五、口径说明")
    out.append("")
    out.append("**阈值**")
    out.append("")
    out.append(f"- SEO 标题：{SEO_TITLE_MIN}~{SEO_TITLE_MAX} 字")
    out.append(f"- meta 描述：{SEO_DESC_MIN}~{SEO_DESC_MAX} 字")
    out.append(f"- 长期未更新：超过 {th.get('stale_days')} 天")
    out.append(f"- 内容过薄：正文纯文本少于 {th.get('thin_chars')} 字")
    out.append("")
    out.append("**效果维度**")
    out.append("")
    out.append(f"- 统计窗口：近 {PERF_WINDOW_DAYS} 天")
    out.append(f"- 零访问：上线满 {NO_TRAFFIC_MIN_AGE_DAYS} 天且窗口内 0 次访问")
    out.append(f"- 读完率偏低：窗口内 PV ≥ {LOW_ENGAGE_MIN_PV} 且平均读完 < {LOW_ENGAGE_SCROLL}%")
    out.append(f"- 高流量零转化：窗口内 PV ≥ {NO_CONV_MIN_PV} 且转化数为 0")
    out.append("")
    out.append("**本报告没有覆盖的检查**（需要外部数据源，接入后可补）")
    out.append("")
    out.append("- 外链质量与数量（需要 Ahrefs / 站长平台数据）")
    out.append("- Core Web Vitals 与移动端渲染（需要真实浏览器跑分）")
    out.append("- 实际收录量与索引状态（需要 Search Console / 百度搜索资源平台）")
    out.append("- 站外链接的死链判定：只校验本系统产出的 `/site/{类型}/{标识}` 形态，")
    out.append("  官网站点路由不在 CMS 管辖范围，拿 slug 去校验只会制造误报")
    out.append("")
    out.append("---")
    out.append("由 Cenkor CMS 内容体检生成。")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

_CSS = """
:root{
  --ink:#1f2937; --ink-2:#4b5563; --ink-3:#6b7280;
  --line:#e5e7eb; --bg:#ffffff; --panel:#f9fafb;
  --ok:#047857; --ok-bg:#ecfdf5;
  --warn:#b45309; --warn-bg:#fffbeb;
  --bad:#b91c1c; --bad-bg:#fef2f2;
  --accent:#2563eb;
}
*{box-sizing:border-box}
body{
  margin:0; padding:0 20px 64px; background:var(--bg); color:var(--ink);
  font:15px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:920px;margin:0 auto}
header{padding:44px 0 28px;border-bottom:2px solid var(--ink)}
h1{margin:0 0 10px;font-size:27px;letter-spacing:-.4px;font-weight:700}
.meta{color:var(--ink-3);font-size:13px;line-height:1.9}
.meta b{color:var(--ink-2);font-weight:600}
h2{margin:44px 0 6px;font-size:19px;font-weight:700;letter-spacing:-.2px}
h2:first-of-type{margin-top:32px}
.lead{color:var(--ink-2);font-size:14px;margin:0 0 16px}
.hero{display:flex;gap:12px;flex-wrap:wrap;margin:26px 0 10px}
.card{flex:1 1 160px;min-width:150px;border:1px solid var(--line);border-radius:10px;padding:16px 18px;background:var(--panel)}
.card .k{font-size:12px;color:var(--ink-3);letter-spacing:.4px;text-transform:uppercase}
.card .v{font-size:30px;font-weight:700;line-height:1.25;letter-spacing:-1px;margin-top:2px}
.card .s{font-size:12px;color:var(--ink-3);margin-top:2px}
.card.main{background:#fff;border-width:2px;border-color:var(--ink);flex:1.35 1 200px}
.card.main .v{font-size:42px}
.v.ok{color:var(--ok)} .v.warn{color:var(--warn)} .v.bad{color:var(--bad)} .v.off{color:var(--ink-3)}
.bar{height:5px;border-radius:3px;background:var(--line);margin-top:10px;overflow:hidden}
.bar i{display:block;height:100%;border-radius:3px}
.bar i.ok{background:var(--ok)} .bar i.warn{background:var(--warn)} .bar i.bad{background:var(--bad)}
.verdict{border-left:3px solid var(--ink);padding:2px 0 2px 14px;margin:20px 0 0;color:var(--ink-2);font-size:14px}
.verdict b{color:var(--ink)}
ol.actions{margin:14px 0 0;padding-left:22px}
ol.actions>li{margin:0 0 18px}
.at{font-weight:600;font-size:15px}
.atag{display:inline-block;margin-left:8px;font-size:11px;font-weight:600;padding:1px 7px;border-radius:99px;vertical-align:1px}
.atag.critical{color:var(--bad);background:var(--bad-bg)}
.atag.warning{color:var(--warn);background:var(--warn-bg)}
.remedy{color:var(--ink-2);font-size:13.5px;margin-top:4px}
.remedy::before{content:"改法　";color:var(--ink-3);font-size:12px}
.involved{color:var(--ink-3);font-size:12.5px;margin-top:3px}
table{width:100%;border-collapse:collapse;margin-top:12px;font-size:13.5px}
th{text-align:left;font-weight:600;color:var(--ink-3);font-size:12px;letter-spacing:.3px;
   padding:8px 10px;border-bottom:1.5px solid var(--line);white-space:nowrap}
td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:none}
td.n{font-variant-numeric:tabular-nums;white-space:nowrap}
.dot{display:inline-block;width:7px;height:7px;border-radius:99px;margin-right:6px;vertical-align:0}
.dot.ok{background:var(--ok)} .dot.warn{background:var(--warn)} .dot.bad{background:var(--bad)}
.badge{display:inline-block;font-size:11.5px;padding:1px 7px;border-radius:5px;margin:1px 3px 1px 0;
       background:var(--panel);border:1px solid var(--line);color:var(--ink-2);white-space:nowrap}
.badge.critical{color:var(--bad);background:var(--bad-bg);border-color:#fecaca}
.badge.warning{color:var(--warn);background:var(--warn-bg);border-color:#fde68a}
.note{background:var(--warn-bg);border:1px solid #fde68a;border-radius:8px;padding:12px 14px;
      font-size:13.5px;color:#78350f;margin:14px 0}
.note.info{background:#eff6ff;border-color:#bfdbfe;color:#1e3a8a}
ul.plain{margin:10px 0 0;padding-left:20px;font-size:13.5px;color:var(--ink-2)}
ul.plain li{margin:5px 0}
.small{font-size:12.5px;color:var(--ink-3)}
footer{margin-top:52px;padding-top:18px;border-top:1px solid var(--line);color:var(--ink-3);font-size:12.5px}
@media print{
  body{padding:0;font-size:12pt}
  .card{break-inside:avoid}
  h2{break-after:avoid}
  tr{break-inside:avoid}
  .wrap{max-width:none}
}
"""


def _bar(score: float) -> str:
    cls = _cls(score)
    return f'<div class="bar"><i class="{cls}" style="width:{max(0.0, min(100.0, score)):.0f}%"></i></div>'


def render_html(report: dict[str, Any], *, site_name: str = "", site_url: str = "") -> str:
    """HTML 版：自带样式，可直接发客户，也可浏览器打印成 PDF。"""
    score = float(report.get("score") or 0)
    verdict, verdict_desc = _verdict(score)
    level = LEVEL_LABEL.get(report.get("level") or "", "")
    dims: dict[str, Any] = report.get("dimension_summary") or {}
    actions: list[dict[str, Any]] = report.get("actions") or []
    summary: dict[str, Any] = report.get("check_summary") or {}
    entries: list[dict[str, Any]] = report.get("entries") or []
    th: dict[str, Any] = report.get("thresholds") or {}
    scanned = int(report.get("scanned") or 0)
    problem_count = int(report.get("problem_count") or 0)
    scope = "内容（含草稿）" if th.get("include_drafts") else "已发布内容"

    score_cls = _cls(score)
    title = f"整站内容与 SEO 体检报告{('：' + site_name) if site_name else ''}"

    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN"><head><meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>{_e(title)}</title><style>{_CSS}</style></head><body><div class='wrap'>",
        "<header>",
        f"<h1>{_e(title)}</h1>",
        "<div class='meta'>",
        f"生成时间 <b>{_e(_local_time(report.get('generated_at') or ''))}</b>",
        f"　·　扫描范围 <b>{scanned}</b> 篇{_e(scope)}",
        f"　·　存在问题 <b>{problem_count}</b> 篇",
        (f"　·　站点 <b>{_e(site_url)}</b>" if site_url else ""),
        "</div></header>",
    ]

    # --- 结论 ---
    parts.append("<h2>结论</h2>")
    parts.append('<div class="hero">')
    parts.append(
        f'<div class="card main"><div class="k">综合得分</div>'
        f'<div class="v {score_cls}">{score:.1f}</div>'
        f"<div class='s'>满分 100 · {_e(level)}</div>{_bar(score)}</div>"
    )
    for d in ("structure", "seo", "performance"):
        info = dims.get(d) or {}
        if not info:
            continue
        enabled = info.get("enabled", True)
        ds = float(info.get("score") or 0)
        if enabled:
            lvl = _score_level(ds)
            parts.append(
                f'<div class="card"><div class="k">{_e(info.get("label") or d)}</div>'
                f'<div class="v {_CSS_CLASS[lvl]}">{ds:.1f}</div>'
                f'<div class="s">{_e(LEVEL_LABEL.get(lvl, ""))}</div>{_bar(ds)}</div>'
            )
        else:
            parts.append(
                f'<div class="card"><div class="k">{_e(info.get("label") or d)}</div>'
                f'<div class="v off">—</div><div class="s">未启用</div></div>'
            )
    parts.append("</div>")
    parts.append(
        f'<p class="verdict"><b>{_e(verdict)}。</b>{_e(verdict_desc)}</p>'
    )

    if not report.get("perf_ready"):
        parts.append(
            '<div class="note info"><b>效果维度未启用。</b>'
            f"埋点还没有采集到任何数据，因此本次不评价「有没有人看」。"
            f"接入埋点后，报告会补充零访问、读完率、转化三类问题 "
            f"（窗口 {PERF_WINDOW_DAYS} 天）。</div>"
        )

    # --- 先改这几件 ---
    parts.append("<h2>先改这几件</h2>")
    if actions:
        parts.append(
            '<p class="lead">按「命中篇数 × 单条扣分」排序 —— 先改影响面最大的。</p>'
        )
        parts.append('<ol class="actions">')
        for a in actions[:8]:
            sev = a.get("severity") or "warning"
            parts.append("<li>")
            parts.append(
                f'<span class="at">{_e(a.get("label"))}</span>'
                f'<span class="atag {_e(sev)}">{_e(SEVERITY_LABEL.get(sev, ""))}</span>'
                f'<span class="small">　{a.get("hit")} 篇　影响面 {a.get("impact")}</span>'
            )
            if a.get("remedy"):
                parts.append(f'<div class="remedy">{_e(a["remedy"])}</div>')
            names = [str(x.get("title") or "") for x in (a.get("entries") or [])]
            if names:
                shown = names[:4]
                tail = f" 等 {len(names)} 篇" if len(names) > 4 else ""
                parts.append(f'<div class="involved">涉及：{_e("；".join(shown))}{_e(tail)}</div>')
            parts.append("</li>")
        parts.append("</ol>")
    else:
        parts.append('<p class="lead">没有需要处理的问题。</p>')

    # --- 问题分布 ---
    parts.append("<h2>问题分布</h2>")
    parts.append(
        "<table><thead><tr><th>维度</th><th>检查项</th><th>严重度</th>"
        "<th class='n'>命中</th><th class='n'>单条扣分</th><th class='n'>影响面</th></tr></thead><tbody>"
    )
    any_hit = False
    for dim_key in ("structure", "seo", "performance"):
        for ck, meta in CHECKS.items():
            if meta["dimension"] != dim_key:
                continue
            hit = int((summary.get(ck) or {}).get("hit") or 0)
            if hit == 0:
                continue
            any_hit = True
            sev = meta["severity"]
            dot = "bad" if sev == "critical" else "warn"
            parts.append(
                f"<tr><td>{_e(DIMENSIONS[dim_key]['label'])}</td>"
                f"<td><span class='dot {dot}'></span>{_e(meta['label'])}</td>"
                f"<td>{_e(SEVERITY_LABEL.get(sev, ''))}</td>"
                f"<td class='n'>{hit}</td><td class='n'>{meta['deduct']}</td>"
                f"<td class='n'>{hit * meta['deduct']}</td></tr>"
            )
    if not any_hit:
        parts.append("<tr><td colspan='6' class='small'>本次扫描没有命中任何检查项。</td></tr>")
    parts.append("</tbody></table>")

    # --- 问题明细 ---
    parts.append("<h2>问题明细</h2>")
    if entries:
        parts.append(
            '<p class="lead">按条目分数升序 —— 分数最低的排在最前面。</p>'
            "<table><thead><tr><th class='n'>分数</th><th>标题</th>"
            "<th class='n'>结构</th><th class='n'>SEO</th><th class='n'>效果</th>"
            "<th>问题</th></tr></thead><tbody>"
        )
        for item in entries[:50]:
            dm = item.get("dimensions") or {}
            badges = "".join(
                f'<span class="badge {_e(i.get("severity") or "")}">{_e(i.get("label"))}</span>'
                for i in (item.get("issues") or [])
            )
            parts.append(
                f"<tr><td class='n'>{item.get('score')}</td>"
                f"<td>{_e(item.get('title'))}</td>"
                f"<td class='n'>{dm.get('structure', '—')}</td>"
                f"<td class='n'>{dm.get('seo', '—')}</td>"
                f"<td class='n'>{dm.get('performance', '—')}</td>"
                f"<td>{badges}</td></tr>"
            )
        parts.append("</tbody></table>")
        if len(entries) > 50:
            parts.append(
                f"<p class='small'>仅列出前 50 篇，共 {len(entries)} 篇存在问题。</p>"
            )
    else:
        parts.append('<p class="lead">没有有问题的内容。</p>')

    # --- 口径 ---
    parts.append("<h2>口径说明</h2>")
    parts.append("<table><tbody>")
    parts.append(
        f"<tr><td class='small'>SEO 标题</td><td>{SEO_TITLE_MIN} ~ {SEO_TITLE_MAX} 字</td></tr>"
        f"<tr><td class='small'>meta 描述</td><td>{SEO_DESC_MIN} ~ {SEO_DESC_MAX} 字</td></tr>"
        f"<tr><td class='small'>长期未更新</td><td>超过 {_e(th.get('stale_days'))} 天</td></tr>"
        f"<tr><td class='small'>内容过薄</td><td>正文纯文本少于 {_e(th.get('thin_chars'))} 字</td></tr>"
        f"<tr><td class='small'>效果统计窗口</td><td>近 {PERF_WINDOW_DAYS} 天</td></tr>"
        f"<tr><td class='small'>零访问</td><td>上线满 {NO_TRAFFIC_MIN_AGE_DAYS} 天且窗口内 0 次访问</td></tr>"
        f"<tr><td class='small'>读完率偏低</td><td>窗口内 PV ≥ {LOW_ENGAGE_MIN_PV} 且平均读完 &lt; {LOW_ENGAGE_SCROLL}%</td></tr>"
        f"<tr><td class='small'>高流量零转化</td><td>窗口内 PV ≥ {NO_CONV_MIN_PV} 且转化数为 0</td></tr>"
        "</tbody></table>"
    )
    parts.append(
        "<h2>本报告未覆盖的检查</h2>"
        '<ul class="plain">'
        "<li>外链质量与数量 —— 需要 Ahrefs、百度搜索资源平台等外部数据源</li>"
        "<li>Core Web Vitals 与移动端渲染 —— 需要真实浏览器跑分</li>"
        "<li>实际收录量与索引状态 —— 需要 Search Console、站点验证</li>"
        "<li>站外链接的死链判定 —— 只校验本系统产出的 "
        "<code>/site/{类型}/{标识}</code> 形态；官网站点路由不在 CMS 管辖范围，"
        "拿内容标识去校验只会制造误报</li>"
        "</ul>"
        "<p class='small'>这些项目需要外部数据源，未接入前不做假结论。"
        "缺项说明不等于「没问题」。</p>"
    )

    parts.append("<footer>由 Cenkor CMS 内容体检生成 · 报告数据为生成时刻快照</footer>")
    parts.append("</div></body></html>")
    return "\n".join(parts)
