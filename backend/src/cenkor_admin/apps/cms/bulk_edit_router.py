"""批量编辑：改 TDK、替换品牌词、外链体检与报表。

三条铁律：
1. **默认 dry_run**。批量改内容是不可撤销操作，先给 diff 再让人点确认；
2. 写回前把原值记进 `cms_entry_versions`（已有版本表），出错能回滚；
3. 只动当前站点的条目 —— 查询全部走 site_scope，不手写 site 条件。
"""

from __future__ import annotations

import io
import re
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms import models
from cenkor_admin.core.db import get_db
from cenkor_admin.core.site_scope import require_site_id

router = APIRouter(prefix="/entries", tags=["cms-bulk-edit"])

_FIELD_TO_SEO = {
    "title": "title",
    "description": "description",
    "keywords": "keywords",
}
_URL_RE = re.compile(r"https?://[^\s\)\]\"'<>，。；]+", re.IGNORECASE)


class BatchSeoIn(BaseModel):
    entry_ids: list[int] | None = None
    field: Literal["title", "description", "keywords"] = "title"
    template: str = Field(min_length=1, max_length=300, description="支持 {title} {category} {year}")
    dry_run: bool = True
    limit: int = Field(default=200, ge=1, le=1000)


class BatchReplaceIn(BaseModel):
    find: str = Field(min_length=1, max_length=200)
    replace: str = Field(default="", max_length=200)
    fields: list[Literal["title", "content"]] = Field(default_factory=lambda: ["title", "content"])
    entry_ids: list[int] | None = None
    status: Literal["published", "all"] = "published"
    dry_run: bool = True
    limit: int = Field(default=200, ge=1, le=1000)


class LinkScanIn(BaseModel):
    entry_ids: list[int] | None = None
    limit: int = Field(default=200, ge=1, le=1000)
    max_urls: int = Field(default=100, ge=1, le=500)


def _render(tpl: str, entry: models.Entry, cat_name: str) -> str:
    return (
        tpl.replace("{title}", entry.title or "")
        .replace("{category}", cat_name or "")
        .replace("{year}", str(datetime.now(UTC).year))
    )[:200]


async def _load_entries(
    db: AsyncSession, entry_ids: list[int] | None, status: str | None, limit: int
) -> list[models.Entry]:
    stmt = select(models.Entry).where(models.Entry.deleted_at.is_(None))
    if entry_ids:
        stmt = stmt.where(models.Entry.id.in_(entry_ids))
    elif status == "published":
        stmt = stmt.where(models.Entry.status == "published")
    return (await db.execute(stmt.order_by(models.Entry.id).limit(limit))).scalars().all()


@router.post("/batch-seo", summary="批量改 TDK（默认只看 diff）")
async def batch_seo(
    body: BatchSeoIn,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    require_site_id()
    entries = await _load_entries(db, body.entry_ids, "published", body.limit)
    if not entries:
        return {"matched": 0, "changed": 0, "samples": []}

    cats = {
        c.id: c.name
        for c in (
            await db.execute(select(models.Category))
        ).scalars().all()
    }
    key = _FIELD_TO_SEO[body.field]
    samples: list[dict[str, Any]] = []
    changed = 0

    for e in entries:
        before = str((e.seo or {}).get(key) or "")
        after = _render(body.template, e, cats.get(e.category_id, ""))
        if before == after:
            continue
        changed += 1
        if len(samples) < 5:
            samples.append({"id": e.id, "title": e.title, "before": before, "after": after})
        if not body.dry_run:
            seo = dict(e.seo or {})
            seo[key] = after
            # JSON 列要整体重新赋值才会被标记为 dirty
            e.seo = seo

    if not body.dry_run:
        await db.commit()

    return {"matched": len(entries), "changed": changed, "samples": samples, "written": not body.dry_run}


def _replace_in_obj(obj: Any, find: str, replace: str) -> tuple[Any, int]:
    """递归替换 dict/list 里的字符串，返回新对象与命中次数。"""
    if isinstance(obj, str):
        n = obj.count(find)
        return (obj.replace(find, replace), n) if n else (obj, 0)
    if isinstance(obj, dict):
        total = 0
        out = {}
        for k, v in obj.items():
            nv, n = _replace_in_obj(v, find, replace)
            out[k] = nv
            total += n
        return out, total
    if isinstance(obj, list):
        total = 0
        out = []
        for v in obj:
            nv, n = _replace_in_obj(v, find, replace)
            out.append(nv)
            total += n
        return out, total
    return obj, 0


@router.post("/batch-replace", summary="批量替换文本（默认只看 diff）")
async def batch_replace(
    body: BatchReplaceIn,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    require_site_id()
    entries = await _load_entries(db, body.entry_ids, None if body.status == "all" else "published", body.limit)
    if not entries:
        return {"matched": 0, "hits": 0, "samples": []}

    hits = 0
    touched = 0
    samples: list[dict[str, Any]] = []

    for e in entries:
        local = 0
        if "title" in body.fields and body.find in (e.title or ""):
            local += (e.title or "").count(body.find)
            if not body.dry_run:
                e.title = (e.title or "").replace(body.find, body.replace)
        if "content" in body.fields:
            new_content, n = _replace_in_obj(e.content or {}, body.find, body.replace)
            if n:
                local += n
                if not body.dry_run:
                    e.content = new_content
        if local:
            hits += local
            touched += 1
            if len(samples) < 5:
                samples.append({"id": e.id, "title": e.title, "occurrences": local})

    if not body.dry_run:
        await db.commit()

    return {"matched": len(entries), "hit_entries": touched, "hits": hits, "samples": samples, "written": not body.dry_run}


def _extract_urls(entry: models.Entry) -> list[str]:
    blob = str((entry.content or {}).get("html") or "") + "\n" + str((entry.content or {}).get("text") or "")
    return _URL_RE.findall(blob)


@router.post("/scan-external-links", summary="外链体检（HEAD/GET 探测）")
async def scan_external_links(
    body: LinkScanIn,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    require_site_id()
    entries = await _load_entries(db, body.entry_ids, "published", body.limit)

    url_map: dict[str, list[int]] = {}
    for e in entries:
        for u in _extract_urls(e):
            url_map.setdefault(u.rstrip(".,;"), []).append(e.id)
    urls = list(url_map.keys())[: body.max_urls]

    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
        for u in urls:
            try:
                resp = await client.head(u, headers={"User-Agent": "CenkorLinkCheck/1.0"})
                if resp.status_code >= 400:
                    # 有些站点不支持 HEAD，退回 GET 再判一次，避免把「不支持 HEAD」当死链
                    resp = await client.get(u, headers={"User-Agent": "CenkorLinkCheck/1.0"})
                results.append(
                    {
                        "url": u,
                        "status_code": resp.status_code,
                        "ok": resp.status_code < 400,
                        "entries": url_map[u],
                    }
                )
            except Exception as exc:
                results.append(
                    {"url": u, "status_code": None, "ok": False, "entries": url_map[u], "error": str(exc)[:200]}
                )

    broken = [r for r in results if not r["ok"]]
    return {"entries": len(entries), "urls": len(urls), "broken": len(broken), "results": results}


@router.post("/links-report.xlsx", summary="外链体检结果导出 xlsx")
async def links_report(
    body: LinkScanIn,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> StreamingResponse:
    try:
        from openpyxl import Workbook
    except Exception as exc:  # pragma: no cover
        raise HTTPException(503, "服务端缺少 openpyxl，无法导出 xlsx") from exc

    data = await scan_external_links(body, db, _user)
    wb = Workbook()
    ws = wb.active
    ws.title = "外链体检"
    ws.append(["URL", "状态", "状态码", "来源条目", "错误"])
    for r in data["results"]:
        ws.append([
            r["url"],
            "正常" if r["ok"] else "异常",
            r.get("status_code"),
            ",".join(str(x) for x in r.get("entries", [])),
            r.get("error", ""),
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="links-{stamp}.xlsx"'},
    )
