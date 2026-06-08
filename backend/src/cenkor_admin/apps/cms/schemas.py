"""CMS App · Pydantic schemas"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ---- Product ----
class ProductBase(BaseModel):
    name: str = Field(..., max_length=120)
    chinese_name: str | None = Field(None, max_length=120)
    slug: str = Field(..., max_length=120)
    tagline: str = Field(..., max_length=200)
    line: Literal["enterprise", "ai", "manufacturing"]
    stack: str = Field(..., max_length=200)
    desc: str
    features: list[Any] = Field(default_factory=list)
    is_flagship: bool = False
    is_open_source: bool = False
    github_url: str | None = None
    demo_url: str | None = None
    website_url: str | None = None
    license: str | None = None
    sort: int = 0
    status: Literal["draft", "published", "archived"] = "published"


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = None
    chinese_name: str | None = None
    tagline: str | None = None
    line: Literal["enterprise", "ai", "manufacturing"] | None = None
    stack: str | None = None
    desc: str | None = None
    features: list[Any] | None = None
    is_flagship: bool | None = None
    is_open_source: bool | None = None
    github_url: str | None = None
    demo_url: str | None = None
    website_url: str | None = None
    license: str | None = None
    sort: int | None = None
    status: Literal["draft", "published", "archived"] | None = None


class ProductOut(ProductBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ---- Case ----
class CaseBase(BaseModel):
    industry: str
    name: str
    desc: str
    tag: str
    href: str | None = None
    sort: int = 0
    status: Literal["draft", "published", "archived"] = "published"


class CaseCreate(CaseBase):
    pass


class CaseUpdate(BaseModel):
    industry: str | None = None
    name: str | None = None
    desc: str | None = None
    tag: str | None = None
    href: str | None = None
    sort: int | None = None
    status: Literal["draft", "published", "archived"] | None = None


class CaseOut(CaseBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ---- Site Config ----
class SiteConfigOut(BaseModel):
    key: str
    value: Any
    description: str | None = None
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SiteConfigUpdate(BaseModel):
    value: Any
    description: str | None = None


# ---- News ----
class NewsBase(BaseModel):
    slug: str = Field(..., max_length=200)
    title: str = Field(..., max_length=200)
    excerpt: str = Field(..., max_length=500)
    content_md: str
    cover_image: str | None = None
    status: Literal["draft", "published", "archived"] = "draft"


class NewsCreate(NewsBase):
    published_at: datetime | None = None


class NewsUpdate(BaseModel):
    title: str | None = None
    excerpt: str | None = None
    content_md: str | None = None
    cover_image: str | None = None
    status: Literal["draft", "published", "archived"] | None = None
    published_at: datetime | None = None


class NewsOut(NewsBase):
    id: int
    view_count: int
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ---- Media ----
class MediaOut(BaseModel):
    id: int
    bucket: str
    key: str
    url: str
    mime: str
    size: int
    width: int | None
    height: int | None
    alt: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MediaUploadResponse(BaseModel):
    """服务端代理上传（前端直接给 file）"""
    id: int
    url: str
    mime: str
    size: int
    width: int | None = None
    height: int | None = None


class MediaPresignRequest(BaseModel):
    """前端直传预签名请求"""
    filename: str
    mime: str
    size: int
    bucket: str | None = None  # 不传则默认 public


class MediaPresignResponse(BaseModel):
    """前端直传预签名响应"""
    upload_url: str
    key: str
    public_url: str
    expires_in: int
    method: str = "PUT"
    headers: dict[str, str] = {}
    media_id: int
