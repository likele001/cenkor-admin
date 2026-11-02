"""系统更新日志自动同步：docs/CHANGELOG.md → 首页「系统更新日志」公告。

设计（2026-11-02）：
- CHANGELOG.md 是**唯一事实源**，格式见文件头说明；版本段 ``## 日期　标题`` + 要点列表。
- 公告 content 里的 ``<!-- AUTOLOG:START/END -->`` 区块是自动托管区，每次同步整体重写：
  里程碑（全部版本行）+ 最新 2 个版本的详情。区块外的历史章节不受影响。
- 触发：scheduler.tick（30s 一轮）。两道指纹防白跑：进程内 md5 缓存 → 库里 extra.autolog_fp。
  均相同则直接返回，**连库都不查**（进程内缓存命中时）。
- 效果：发版只需更新 CHANGELOG.md（scp/commit），无需重启服务，30 秒内公告自动刷新。
- 安全：本模块任何异常只 warn 不抛，绝不影响调度循环与平台启动。
"""
from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select

from cenkor_admin.apps.announcements.models import Announcement
from cenkor_admin.core.db import AsyncSessionLocal

log = structlog.get_logger()

# CHANGELOG 候选路径：环境变量 > 仓库根推断 > cwd 相对 > 绝对路径兜底
_CANDIDATES = [
    Path(__file__).resolve().parents[5] / "docs" / "CHANGELOG.md",  # backend/src/cenkor_admin/apps/x.py → 仓库根
    Path("../docs/CHANGELOG.md"),
    Path("/www/wwwroot/cenkor-admin/docs/CHANGELOG.md"),
]

_VER_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*　?\s*(.+?)\s*$")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_INLINE_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_GROUP_RE = re.compile(r"^\*\*【(.+?)】\*\*\s*$")
_BLOCK_RE = re.compile(r"<!-- AUTOLOG:START -->.*?<!-- AUTOLOG:END -->", re.S)
_SUMMARY_DATE_RE = re.compile(r"截至\s*\d{4}-\d{2}-\d{2}")

_DETAIL_COUNT = 2  # 「最新系统更新」展示最近 N 个版本的详情

# 进程内指纹缓存：命中且未变时零数据库查询
_last_fp: str | None = None
_SYNCING: set[int] = set()  # 防重入（公告 id）


def _changelog_path() -> Path | None:
    env = __import__("os").environ.get("AUTOLOG_CHANGELOG_PATH")
    if env:
        return Path(env)
    for p in _CANDIDATES:
        if p.is_file():
            return p
    return None


def _inline(s: str) -> str:
    """行内 markdown 小集：`code` → <code>，**b** → <b>。"""
    s = _INLINE_CODE_RE.sub(r"<code>\1</code>", s)
    s = _INLINE_BOLD_RE.sub(r"<b>\1</b>", s)
    return s


def _parse(md: str) -> list[dict[str, Any]]:
    """解析 CHANGELOG → [{date, title, star, body_html}]，文件顶 = 列表头。"""
    versions: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for raw in md.splitlines():
        m = _VER_RE.match(raw)
        if m:
            if cur:
                versions.append(cur)
            title = m.group(2)
            star = "⭐" in title or "★" in title
            cur = {
                "date": m.group(1),
                "title": title.replace("⭐", "").replace("★", "").strip(),
                "star": star,
                "lines": [],
            }
            continue
        if cur is None or raw.strip().startswith((">", "#")):
            continue  # 文件头说明 / 非版本段标题
        s = raw.strip()
        if s:
            cur["lines"].append(s)
    if cur:
        versions.append(cur)
    return versions


def _render_body(lines: list[str]) -> list[str]:
    """版本段正文行 → HTML 行（分组标题 / 连续列表聚合）。"""
    out: list[str] = []
    in_list = False
    for s in lines:
        g = _GROUP_RE.match(s)
        if g:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p><b>【{g.group(1)}】</b></p>")
        elif s.startswith(("- ", "* ")):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(s[2:].strip())}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            # 普通段落行（版本描述等）
            out.append(f"<p>{_inline(s)}</p>")
    if in_list:
        out.append("</ul>")
    return out


def _render_block(versions: list[dict[str, Any]]) -> str:
    """CHANGELOG 全量 → 公告托管区块 HTML（一、里程碑 + 二、最新更新）。"""
    if not versions:
        return ""
    # 一、项目里程碑：全部版本一行一条
    ms = [
        f"<li>{v['date']}　{v['title']}{'（重点版本）' if v['star'] else ''}</li>"
        for v in versions
    ]
    parts = [
        "<!-- AUTOLOG:START -->",
        "<h3>一、项目里程碑</h3>",
        "<ul>",
        *ms,
        "</ul>",
    ]
    # 二、最新系统更新：最近 N 个版本的详情
    detail = versions[:_DETAIL_COUNT]
    if len(detail) >= 2 and detail[0]["date"] != detail[1]["date"]:
        rng = f"{detail[1]['date']} ~ {detail[0]['date'][5:]}"
    else:
        rng = detail[0]["date"]
    parts.append(f"<h3>二、最新系统更新（{rng}）</h3>")
    for v in detail:
        parts.append(f"<p><b>{v['date']}　{v['title']}</b></p>")
        parts.extend(_render_body(v["lines"]))
    parts.append("<!-- AUTOLOG:END -->")
    return "\n".join(parts)


def _latest_date(versions: list[dict[str, Any]]) -> str:
    return versions[0]["date"] if versions else ""


async def sync_if_changed(*, force: bool = False) -> bool:
    """检查 CHANGELOG 指纹，变化则同步进公告。返回是否实际写库。

    force=True 时跳过指纹比对直接同步（手动触发用）。
    """
    global _last_fp
    path = _changelog_path()
    if path is None:
        return False
    try:
        md = path.read_text(encoding="utf-8")
    except OSError as e:
        log.warning("announcements.autolog.read_failed", path=str(path), error=str(e))
        return False

    fp = hashlib.md5(md.encode()).hexdigest()
    if not force and fp == _last_fp:
        return False  # 文件没变（进程内缓存），连库都不查

    versions = _parse(md)
    if not versions:
        _last_fp = fp
        return False
    block = _render_block(versions)
    if not block:
        _last_fp = fp
        return False
    latest = _latest_date(versions)

    # 查目标公告：优先找已带托管区块的（唯一），否则找 pinned 的日志公告
    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(Announcement)
            .where(
                Announcement.deleted_at.is_(None),
                Announcement.is_published.is_(True),
                Announcement.content.like("%AUTOLOG:START%"),
            )
            .order_by(Announcement.id)
            .limit(1)
        )).scalar()

        if row is None:
            # 首次接入：找标题含「系统更新日志」的置顶公告，插入托管区块
            row = (await db.execute(
                select(Announcement)
                .where(
                    Announcement.deleted_at.is_(None),
                    Announcement.is_published.is_(True),
                    Announcement.title.like("%系统更新日志%"),
                )
                .order_by(Announcement.id)
                .limit(1)
            )).scalar()
            if row is None:
                log.warning("announcements.autolog.no_target_announcement")
                _last_fp = fp
                return False
            if "AUTOLOG:START" not in (row.content or ""):
                anchor = "<h3>一、项目里程碑</h3>"
                if anchor in row.content:
                    # 区块替代原有「一、二」两节：从锚点到下一个 <h3> 之间全部替换
                    row.content = _BLOCK_RE.sub("", row.content)  # 先清旧区块（幂等）
                    pat = re.compile(
                        re.escape(anchor) + r".*?(?=<h3>三、)", re.S)
                    if pat.search(row.content):
                        row.content = pat.sub(block, row.content, count=1)
                    else:
                        row.content = block + "\n" + row.content
                else:
                    row.content = block + "\n" + row.content
        else:
            row.content = _BLOCK_RE.sub(block, row.content, count=1)

        if latest:
            row.summary = _SUMMARY_DATE_RE.sub(f"截至 {latest}", row.summary or "")

        extra = dict(row.extra or {})
        if extra.get("autolog_fp") == fp and not force:
            _last_fp = fp
            return False  # 库里已是这版（多进程/重启场景兜底）
        extra["autolog_fp"] = fp
        extra["autolog_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        row.extra = extra
        await db.commit()
        log.info("announcements.autolog.synced", versions=len(versions),
                 latest=latest, announcement_id=row.id)
    _last_fp = fp
    return True
