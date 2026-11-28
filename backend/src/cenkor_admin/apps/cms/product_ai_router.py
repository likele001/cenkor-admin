"""产品内容专用链路：一次生成卖点、简介、参数亮点、TDK。

和文章的区别：产品页读者是买主，要的是「你是不是我要的东西、凭什么信你」，
所以这里不生成散文，只生成可直接上架的结构化字段。
"""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms import models
from cenkor_admin.core.db import get_db
from cenkor_admin.core.llm import get_llm
from cenkor_admin.core.site_scope import require_site_id

router = APIRouter(prefix="/products", tags=["cms-product-ai"])

Section = Literal["tagline", "desc", "features", "seo"]

_SYSTEM = """你是工业品电商的文案，写中文产品页。只输出 JSON：

{
  "tagline": "25 字内一句话卖点，说清给谁解决什么",
  "desc": "300-500 字：解决什么问题、关键能力、适用场景、交付与服务",
  "features": [{"name": "参数或能力名", "value": "具体数值或一句说明"}],
  "seo": {"title": "60 字内含核心词", "description": "80 字内", "keywords": "逗号分隔 5-8 个"}
}

要求：
1. 不编造具体数字；用户没给的参数就写能力描述，不要虚构公差、压力、产量；
2. 不写「行业领先」「赋能」这类空话；
3. features 给 4-8 条。"""


class GenerateIn(BaseModel):
    brief: str | None = Field(default=None, max_length=3000)
    sections: list[Section] = Field(default_factory=lambda: ["tagline", "desc", "features", "seo"])
    overwrite: bool = True


@router.post("/{product_id}/generate", summary="按产品生成文案与 TDK")
async def generate(
    product_id: int,
    body: GenerateIn,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    require_site_id()
    product = (
        await db.execute(select(models.Product).where(models.Product.id == product_id))
    ).scalars().first()
    if product is None or getattr(product, "deleted_at", None) is not None:
        raise HTTPException(404, "产品不存在")

    user_msg = "\n".join(
        [
            f"产品名称：{product.name}",
            f"中文名：{product.chinese_name or '—'}",
            f"产品线：{product.line or '—'}",
            f"技术栈：{product.stack or '—'}",
            f"现有简介：{(product.desc or '')[:800]}",
            f"补充说明：{body.brief or '—'}",
        ]
    )

    try:
        llm = get_llm()
        _raw, result = await llm.chat_json(
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user_msg}],
            temperature=0.4,
            max_tokens=2000,
        )
    except Exception as exc:
        raise HTTPException(503, f"AI 生成失败：{exc}") from exc
    if not isinstance(result, dict):
        raise HTTPException(503, "AI 返回的不是 JSON 对象")

    updated: list[str] = []
    changed: dict[str, Any] = {}

    if (
        "tagline" in body.sections
        and result.get("tagline")
        and (body.overwrite or not (product.tagline or "").strip())
    ):
        product.tagline = str(result["tagline"])[:200]
        updated.append("tagline")
        changed["tagline"] = product.tagline

    if (
        "desc" in body.sections
        and result.get("desc")
        and (body.overwrite or not (product.desc or "").strip())
    ):
        product.desc = str(result["desc"])
        updated.append("desc")
        changed["desc"] = product.desc

    if "features" in body.sections and isinstance(result.get("features"), list):
        feats = [
            {"name": str(f.get("name") or "")[:60], "value": str(f.get("value") or "")[:200]}
            for f in result["features"]
            if isinstance(f, dict) and f.get("name")
        ][:12]
        if feats and (body.overwrite or not (product.features or [])):
            product.features = feats
            updated.append("features")
            changed["features"] = feats

    seo = result.get("seo") if isinstance(result.get("seo"), dict) else {}
    if (
        "seo" in body.sections
        and seo
        and (body.overwrite or not (product.seo_title or "").strip())
    ):
        product.seo_title = str(seo.get("title") or "")[:200] or product.seo_title
        product.seo_description = (
            str(seo.get("description") or "")[:2000] or product.seo_description
        )
        product.seo_keywords = str(seo.get("keywords") or "")[:500] or product.seo_keywords
        updated.append("seo")
        changed["seo"] = {
            "title": product.seo_title,
            "description": product.seo_description,
            "keywords": product.seo_keywords,
        }

    if not updated:
        raise HTTPException(409, "没有可写入的字段（可能全部已有内容且未开启覆盖）")

    await db.commit()
    return {"product_id": product.id, "updated": updated, "changed": changed}


@router.post("/{product_id}/preview", summary="只返回生成结果，不写入")
async def preview(
    product_id: int,
    body: GenerateIn,
    db: AsyncSession = Depends(get_db),
    _user: auth_models.User = Depends(get_current_user),
) -> dict[str, Any]:
    """干跑：前端可以先看文案，不满意再点写入。"""
    require_site_id()
    product = (
        await db.execute(select(models.Product).where(models.Product.id == product_id))
    ).scalars().first()
    if product is None:
        raise HTTPException(404, "产品不存在")

    user_msg = json.dumps(
        {
            "产品名称": product.name,
            "中文名": product.chinese_name,
            "产品线": product.line,
            "技术栈": product.stack,
            "现有简介": (product.desc or "")[:800],
            "补充说明": body.brief or "",
        },
        ensure_ascii=False,
    )
    try:
        llm = get_llm()
        _raw, result = await llm.chat_json(
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user_msg}],
            temperature=0.4,
            max_tokens=2000,
        )
    except Exception as exc:
        raise HTTPException(503, f"AI 生成失败：{exc}") from exc
    return {"product_id": product_id, "draft": result}
