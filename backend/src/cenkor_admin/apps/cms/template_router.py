"""CMS 模板预览 API（后台管理）"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from cenkor_admin.core.template_engine import (
    render_template,
    render_template_safe,
    validate_template,
)

router = APIRouter()


class TemplateRenderRequest(BaseModel):
    template: str = Field(..., description="Liquid 模板字符串")
    data: dict[str, Any] = Field(default_factory=dict, description="模板数据")


class TemplateValidateRequest(BaseModel):
    template: str


@router.post("/templates/render")
async def templates_render(body: TemplateRenderRequest):
    """渲染 Liquid 模板"""
    if not body.template:
        return {"rendered": "", "error": None}

    rendered, error = render_template_safe(body.template, body.data)
    if error:
        raise HTTPException(400, f"模板渲染失败: {error}")
    return {"rendered": rendered, "error": None}


@router.post("/templates/validate")
async def templates_validate(body: TemplateValidateRequest):
    """校验模板语法"""
    valid, error = validate_template(body.template)
    return {"valid": valid, "error": error}


@router.post("/templates/preview")
async def templates_preview(body: TemplateRenderRequest):
    """模板预览（与 render 相同，但专门用于 CMS 模板编辑器实时预览）"""
    try:
        rendered = render_template(body.template, body.data)
    except Exception as e:
        return {"rendered": "", "error": str(e), "ok": False}
    return {"rendered": rendered, "error": None, "ok": True}
