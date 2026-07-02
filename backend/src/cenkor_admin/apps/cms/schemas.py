"""CMS App · Pydantic schemas"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cenkor_admin.apps.cms.field_types import FIELD_TYPES


# ============================================================
# Content Type
# ============================================================

class ContentTypeCreate(BaseModel):
    key: str = Field(..., max_length=60, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(..., max_length=80)
    description: str | None = None
    icon: str | None = Field(None, max_length=20)
    supports_category: bool = True
    supports_tags: bool = True
    default_list_template: str | None = None
    default_detail_template: str | None = None


class ContentTypeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    supports_category: bool | None = None
    supports_tags: bool | None = None
    default_list_template: str | None = None
    default_detail_template: str | None = None


class FieldGroupOut(BaseModel):
    id: int
    key: str
    label: str
    sort: int
    icon: str | None = None
    model_config = ConfigDict(from_attributes=True)


class FieldOptionOut(BaseModel):
    id: int
    value: str
    label: str
    color: str | None = None
    sort: int
    model_config = ConfigDict(from_attributes=True)


class FieldDefinitionOut(BaseModel):
    id: int
    content_type_id: int
    field_key: str
    label: str
    field_type: str
    required: bool
    default_value: str | None = None
    options: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    group_id: int | None = None
    sort: int
    status: str
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime
    field_options: list[FieldOptionOut] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class ContentTypeOut(BaseModel):
    id: int
    key: str
    name: str
    description: str | None = None
    icon: str | None = None
    supports_category: bool
    supports_tags: bool
    default_list_template: str | None = None
    default_detail_template: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    field_groups: list[FieldGroupOut] = Field(default_factory=list)
    field_definitions: list[FieldDefinitionOut] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class ContentTypeListItem(BaseModel):
    id: int
    key: str
    name: str
    description: str | None = None
    icon: str | None = None
    supports_category: bool
    supports_tags: bool
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Field Group
# ============================================================

class FieldGroupCreate(BaseModel):
    key: str = Field(..., max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(..., max_length=80)
    sort: int = 0
    icon: str | None = Field(None, max_length=20)


class FieldGroupUpdate(BaseModel):
    label: str | None = None
    sort: int | None = None
    icon: str | None = None


class ReorderItem(BaseModel):
    id: int
    sort: int


class ReorderRequest(BaseModel):
    items: list[ReorderItem]


# ============================================================
# Field Definition
# ============================================================

class FieldDefinitionCreate(BaseModel):
    field_key: str = Field(..., max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(..., max_length=80)
    field_type: str = Field(..., description="字段类型")
    required: bool = False
    default_value: str | None = None
    options: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    group_id: int | None = None
    sort: int = 0
    status: str = "active"

    @classmethod
    def validate_field_type(cls, v: str) -> str:
        if v not in FIELD_TYPES:
            raise ValueError(f"Invalid field_type: {v}. Must be one of {FIELD_TYPES}")
        return v

    def model_post_init(self, __context: Any) -> None:
        self.field_type = self.validate_field_type(self.field_type)


class FieldDefinitionUpdate(BaseModel):
    label: str | None = None
    field_type: str | None = None
    required: bool | None = None
    default_value: str | None = None
    options: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    group_id: int | None = None
    sort: int | None = None
    status: str | None = None

    @classmethod
    def validate_field_type(cls, v: str | None) -> str | None:
        if v is not None and v not in FIELD_TYPES:
            raise ValueError(f"Invalid field_type: {v}. Must be one of {FIELD_TYPES}")
        return v

    def model_post_init(self, __context: Any) -> None:
        if self.field_type is not None:
            self.field_type = self.validate_field_type(self.field_type)


# ============================================================
# Field Option
# ============================================================

class FieldOptionCreate(BaseModel):
    definition_id: int
    value: str = Field(..., max_length=80)
    label: str = Field(..., max_length=80)
    color: str | None = Field(None, max_length=20)
    sort: int = 0


class FieldOptionUpdate(BaseModel):
    value: str | None = None
    label: str | None = None
    color: str | None = None
    sort: int | None = None


# ============================================================
# Category
# ============================================================

class CategoryCreate(BaseModel):
    content_type_key: str = Field(..., max_length=60)
    parent_id: int | None = None
    slug: str = Field(..., max_length=80)
    name: str = Field(..., max_length=80)
    icon: str | None = Field(None, max_length=20)
    color: str | None = Field(None, max_length=20)
    sort: int = 0


class CategoryUpdate(BaseModel):
    parent_id: int | None = None
    slug: str | None = None
    name: str | None = None
    icon: str | None = None
    color: str | None = None
    sort: int | None = None
    status: str | None = None


class CategoryOut(BaseModel):
    id: int
    content_type_id: int
    parent_id: int | None = None
    slug: str
    name: str
    icon: str | None = None
    color: str | None = None
    sort: int
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CategoryTreeOut(CategoryOut):
    children: list["CategoryTreeOut"] = Field(default_factory=list)


# ============================================================
# Tag
# ============================================================

class TagCreate(BaseModel):
    content_type_key: str = Field(..., max_length=60)
    slug: str = Field(..., max_length=80)
    name: str = Field(..., max_length=80)
    color: str | None = Field(None, max_length=20)


class TagUpdate(BaseModel):
    slug: str | None = None
    name: str | None = None
    color: str | None = None


class TagOut(BaseModel):
    id: int
    content_type_id: int
    slug: str
    name: str
    color: str | None = None
    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Product
# ============================================================

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
    custom_fields: dict[str, Any] | None = None
    github_url: str | None = None
    demo_url: str | None = None
    website_url: str | None = None
    license: str | None = None
    sort: int = 0
    status: Literal["draft", "published", "archived"] = "published"
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = None
    chinese_name: str | None = None
    slug: str | None = None
    tagline: str | None = None
    line: Literal["enterprise", "ai", "manufacturing"] | None = None
    stack: str | None = None
    desc: str | None = None
    features: list[Any] | None = None
    is_flagship: bool | None = None
    is_open_source: bool | None = None
    custom_fields: dict[str, Any] | None = None
    github_url: str | None = None
    demo_url: str | None = None
    website_url: str | None = None
    license: str | None = None
    sort: int | None = None
    status: Literal["draft", "published", "archived"] | None = None


class ProductOut(ProductBase):
    id: int
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Case
# ============================================================

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
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Site Config
# ============================================================

class SiteConfigOut(BaseModel):
    key: str
    value: Any
    description: str | None = None
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SiteConfigUpdate(BaseModel):
    value: Any
    description: str | None = None


# ============================================================
# News
# ============================================================

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
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    view_count: int
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Media
# ============================================================

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
    id: int
    url: str
    mime: str
    size: int
    width: int | None = None
    height: int | None = None


class MediaPresignRequest(BaseModel):
    filename: str
    mime: str
    size: int
    bucket: str | None = None


class MediaPresignResponse(BaseModel):
    upload_url: str
    key: str
    public_url: str
    expires_in: int
    method: str = "PUT"
    headers: dict[str, str] = {}
    media_id: int
