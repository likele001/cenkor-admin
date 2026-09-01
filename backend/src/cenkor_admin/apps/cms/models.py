"""CMS App · ORM 模型（PG 优先，SQLAlchemy 写法兼容 MySQL）"""

from __future__ import annotations



from datetime import datetime

from typing import Any



from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey, func, Index, UniqueConstraint

from sqlalchemy.orm import Mapped, mapped_column, relationship



from cenkor_admin.core.compat import json_column

from cenkor_admin.core.db import Base





# ============================================================

# 内容引擎元数据

# ============================================================





class ContentType(Base):

    """内容类型（元数据，支持未来扩展）"""

    __tablename__ = "cms_content_types"



    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    key: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)

    name: Mapped[str] = mapped_column(String(80), nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    icon: Mapped[str | None] = mapped_column(String(20), nullable=True)

    supports_category: Mapped[bool] = mapped_column(Boolean, default=True)

    supports_tags: Mapped[bool] = mapped_column(Boolean, default=True)

    translatable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    default_list_template: Mapped[str | None] = mapped_column(Text, nullable=True)

    default_detail_template: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    updated_at: Mapped[datetime] = mapped_column(

        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()

    )

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)



    field_groups: Mapped[list["FieldGroup"]] = relationship(

        "FieldGroup", back_populates="content_type", cascade="all, delete-orphan", lazy="selectin"

    )

    field_definitions: Mapped[list["FieldDefinition"]] = relationship(

        "FieldDefinition", back_populates="content_type", cascade="all, delete-orphan", lazy="selectin"

    )





class FieldGroup(Base):

    """字段分组（实现 tabs 分组）"""

    __tablename__ = "cms_field_groups"



    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    content_type_id: Mapped[int] = mapped_column(

        Integer, ForeignKey("cms_content_types.id", ondelete="CASCADE"), nullable=False

    )

    key: Mapped[str] = mapped_column(String(80), nullable=False)

    label: Mapped[str] = mapped_column(String(80), nullable=False)

    sort: Mapped[int] = mapped_column(Integer, default=0)

    icon: Mapped[str | None] = mapped_column(String(20), nullable=True)



    content_type: Mapped["ContentType"] = relationship("ContentType", back_populates="field_groups")



    __table_args__ = (

        UniqueConstraint("content_type_id", "key", name="uq_field_group_ct_key"),

    )





class FieldDefinition(Base):

    """字段定义（字段元数据）"""

    __tablename__ = "cms_field_definitions"



    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    content_type_id: Mapped[int] = mapped_column(

        Integer, ForeignKey("cms_content_types.id", ondelete="CASCADE"), nullable=False

    )

    field_key: Mapped[str] = mapped_column(String(80), nullable=False)

    label: Mapped[str] = mapped_column(String(80), nullable=False)

    field_type: Mapped[str] = mapped_column(String(20), nullable=False)

    required: Mapped[bool] = mapped_column(Boolean, default=False)

    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    options: Mapped[dict[str, Any] | None] = mapped_column(json_column(), nullable=True)

    validation: Mapped[dict[str, Any] | None] = mapped_column(json_column(), nullable=True)

    group_id: Mapped[int | None] = mapped_column(

        Integer, ForeignKey("cms_field_groups.id", ondelete="SET NULL"), nullable=True

    )

    sort: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(20), default="active")

    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    updated_at: Mapped[datetime] = mapped_column(

        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()

    )



    content_type: Mapped["ContentType"] = relationship("ContentType", back_populates="field_definitions")

    field_group: Mapped["FieldGroup | None"] = relationship("FieldGroup")

    field_options: Mapped[list["FieldOption"]] = relationship(

        "FieldOption", back_populates="definition", cascade="all, delete-orphan", lazy="selectin"

    )



    __table_args__ = (

        UniqueConstraint("content_type_id", "field_key", name="uq_field_def_ct_key"),

    )





class FieldOption(Base):

    """字段选项（select/multi_select 的候选项）"""

    __tablename__ = "cms_field_options"



    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    definition_id: Mapped[int] = mapped_column(

        Integer, ForeignKey("cms_field_definitions.id", ondelete="CASCADE"), nullable=False

    )

    value: Mapped[str] = mapped_column(String(80), nullable=False)

    label: Mapped[str] = mapped_column(String(80), nullable=False)

    color: Mapped[str | None] = mapped_column(String(20), nullable=True)

    sort: Mapped[int] = mapped_column(Integer, default=0)



    definition: Mapped["FieldDefinition"] = relationship("FieldDefinition", back_populates="field_options")





class Category(Base):

    """分类（每套独立，3+ 级层级）"""

    __tablename__ = "cms_categories"



    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    content_type_id: Mapped[int] = mapped_column(

        Integer, ForeignKey("cms_content_types.id", ondelete="CASCADE"), nullable=False

    )

    parent_id: Mapped[int | None] = mapped_column(

        Integer, ForeignKey("cms_categories.id", ondelete="SET NULL"), nullable=True

    )

    slug: Mapped[str] = mapped_column(String(80), nullable=False)

    name: Mapped[str] = mapped_column(String(80), nullable=False)

    icon: Mapped[str | None] = mapped_column(String(20), nullable=True)

    color: Mapped[str | None] = mapped_column(String(20), nullable=True)

    sort: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(20), default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    updated_at: Mapped[datetime] = mapped_column(

        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()

    )

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)



    parent: Mapped["Category | None"] = relationship("Category", remote_side="Category.id", backref="children")



    __table_args__ = (

        UniqueConstraint("content_type_id", "slug", name="uq_category_ct_slug"),

        Index("ix_cms_categories_ct_parent", "content_type_id", "parent_id"),

    )





class Tag(Base):

    """标签"""

    __tablename__ = "cms_tags"



    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    content_type_id: Mapped[int] = mapped_column(

        Integer, ForeignKey("cms_content_types.id", ondelete="CASCADE"), nullable=False

    )

    slug: Mapped[str] = mapped_column(String(80), nullable=False)

    name: Mapped[str] = mapped_column(String(80), nullable=False)

    color: Mapped[str | None] = mapped_column(String(20), nullable=True)



    __table_args__ = (

        UniqueConstraint("content_type_id", "slug", name="uq_tag_ct_slug"),

    )





class ContentTag(Base):

    """内容-标签多对多"""

    __tablename__ = "cms_content_tags"



    content_type_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    content_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    tag_id: Mapped[int] = mapped_column(

        Integer, ForeignKey("cms_tags.id", ondelete="CASCADE"), primary_key=True

    )





class Entry(Base):

    """通用内容表"""

    __tablename__ = "cms_entries"



    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    content_type_id: Mapped[int] = mapped_column(

        Integer, ForeignKey("cms_content_types.id", ondelete="CASCADE"), nullable=False, index=True

    )

    slug: Mapped[str | None] = mapped_column(String(120), nullable=True)

    title: Mapped[str] = mapped_column(String(200), nullable=False)

    content: Mapped[dict[str, Any]] = mapped_column(json_column(), default=dict)

    custom_fields: Mapped[dict[str, Any]] = mapped_column(json_column(), default=dict)

    seo: Mapped[dict[str, Any] | None] = mapped_column(json_column(), nullable=True, default=dict)

    category_id: Mapped[int | None] = mapped_column(

        Integer, ForeignKey("cms_categories.id", ondelete="SET NULL"), nullable=True

    )

    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)

    author_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sort: Mapped[int] = mapped_column(Integer, default=0)

    view_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    updated_at: Mapped[datetime] = mapped_column(

        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()

    )

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)



    category: Mapped["Category | None"] = relationship("Category")

    tags: Mapped[list["ContentTag"]] = relationship(

        "ContentTag", primaryjoin="Entry.id == foreign(ContentTag.content_id)", cascade="all, delete-orphan"

    )



    __table_args__ = (

        UniqueConstraint("content_type_id", "slug", name="uq_entry_ct_slug"),

        Index("ix_cms_entries_ct_status", "content_type_id", "status"),

        Index("ix_cms_entries_custom_fields", "custom_fields", postgresql_using="gin"),

    )


class EntryVersion(Base):

    """内容版本快照（M1·P0 版本控制）。

    每次 Entry 保存（创建/更新/回滚）都写一条不可变快照；
    通过 ``POST /entries/{id}/restore/{v}`` 一键回滚。
    """

    __tablename__ = "cms_entry_versions"



    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    entry_id: Mapped[int] = mapped_column(

        Integer, ForeignKey("cms_entries.id", ondelete="CASCADE"), nullable=False, index=True

    )

    version: Mapped[int] = mapped_column(Integer, nullable=False)

    data: Mapped[dict[str, Any]] = mapped_column(json_column(), default=dict)

    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())



    __table_args__ = (

        UniqueConstraint("entry_id", "version", name="uq_entry_version"),

    )


class EntryReviewLog(Base):

    """发布审批记录（M2·P1 2.4 发布工作流）"""

    __tablename__ = "cms_entry_review_log"



    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    entry_id: Mapped[int] = mapped_column(

        Integer, ForeignKey("cms_entries.id", ondelete="CASCADE"), nullable=False, index=True

    )

    action: Mapped[str] = mapped_column(String(20), nullable=False)

    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    reviewer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())





# ============================================================

# 原有 CMS 表（保留，加 custom_fields）

# ============================================================





class Product(Base):

    """产品表"""

    __tablename__ = "cms_products"



    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)

    name: Mapped[str] = mapped_column(String(120), index=True)

    chinese_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    tagline: Mapped[str] = mapped_column(String(200))

    line: Mapped[str] = mapped_column(String(50), index=True)

    stack: Mapped[str] = mapped_column(String(200))

    desc: Mapped[str] = mapped_column(Text)

    features: Mapped[list[Any]] = mapped_column(json_column(), default=list)

    is_flagship: Mapped[bool] = mapped_column(Boolean, default=False)

    is_open_source: Mapped[bool] = mapped_column(Boolean, default=False)

    github_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    demo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    license: Mapped[str | None] = mapped_column(String(50), nullable=True)

    sort: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(20), default="published")

    custom_fields: Mapped[dict[str, Any]] = mapped_column(json_column(), default=dict)

    seo_title: Mapped[str | None] = mapped_column(String(200), nullable=True)

    seo_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    seo_keywords: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    updated_at: Mapped[datetime] = mapped_column(

        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()

    )

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)



    __table_args__ = (

        Index("ix_cms_products_line_status", "line", "status"),

    )





class Case(Base):

    """客户案例"""

    __tablename__ = "cms_cases"



    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    industry: Mapped[str] = mapped_column(String(80), index=True)

    name: Mapped[str] = mapped_column(String(200))

    desc: Mapped[str] = mapped_column(Text)

    tag: Mapped[str] = mapped_column(String(80))

    href: Mapped[str | None] = mapped_column(String(500), nullable=True)

    sort: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(20), default="published")

    custom_fields: Mapped[dict[str, Any]] = mapped_column(json_column(), default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    updated_at: Mapped[datetime] = mapped_column(

        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()

    )

    seo_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    seo_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    seo_keywords: Mapped[str | None] = mapped_column(String(500), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)





class News(Base):

    """新闻 / 博客"""

    __tablename__ = "cms_news"



    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)

    title: Mapped[str] = mapped_column(String(200), index=True)

    excerpt: Mapped[str] = mapped_column(String(500))

    content_md: Mapped[str] = mapped_column(Text)

    cover_image: Mapped[str | None] = mapped_column(String(500), nullable=True)

    author_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    view_count: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(20), default="draft")

    custom_fields: Mapped[dict[str, Any]] = mapped_column(json_column(), default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    updated_at: Mapped[datetime] = mapped_column(

        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()

    )

    seo_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    seo_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    seo_keywords: Mapped[str | None] = mapped_column(String(500), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)





class SiteConfig(Base):

    """站点配置 KV（key-value，value 为 JSON）"""

    __tablename__ = "cms_site_config"



    key: Mapped[str] = mapped_column(String(80), primary_key=True)

    value: Mapped[Any] = mapped_column(json_column())

    description: Mapped[str | None] = mapped_column(String(200), nullable=True)

    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(

        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()

    )





class Media(Base):

    """媒体库（图片/文件）"""

    __tablename__ = "cms_media"



    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    bucket: Mapped[str] = mapped_column(String(80), index=True)

    key: Mapped[str] = mapped_column(String(500), index=True)

    url: Mapped[str] = mapped_column(String(1000))

    mime: Mapped[str] = mapped_column(String(120), index=True)

    size: Mapped[int] = mapped_column(Integer)

    width: Mapped[int | None] = mapped_column(Integer, nullable=True)

    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    alt: Mapped[str] = mapped_column(String(200), default="")

    uploader_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Language(Base):

    """站点语言（M1·P0 多语言 i18n）"""

    __tablename__ = "cms_languages"



    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    name: Mapped[str] = mapped_column(String(80), nullable=False)

    flag: Mapped[str | None] = mapped_column(String(20), nullable=True)

    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    sort: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    updated_at: Mapped[datetime] = mapped_column(

        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()

    )



class EntryTranslation(Base):

    """条目翻译（M1·P0 多语言 i18n）。

    主表 cms_entries 保留默认语言；其余语言存本表 field_values JSONB。
    公开 API 通过 ``?lang=`` 读取并覆盖 title/content/custom_fields。
    """

    __tablename__ = "cms_entry_translations"



    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    entry_id: Mapped[int] = mapped_column(

        Integer, ForeignKey("cms_entries.id", ondelete="CASCADE"), nullable=False, index=True

    )

    lang: Mapped[str] = mapped_column(String(20), nullable=False)

    field_values: Mapped[dict[str, Any]] = mapped_column(json_column(), default=dict)

    status: Mapped[str] = mapped_column(String(20), default="draft")

    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    updated_at: Mapped[datetime] = mapped_column(

        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()

    )



    __table_args__ = (

        UniqueConstraint("entry_id", "lang", name="uq_entry_translation_lang"),

    )


class EntryPreview(Base):

    """条目暂存预览（M4·P3 4.4 staging）。

    草稿/已通过内容可生成带 token 的预览链接，发布后自动失效。
    """

    __tablename__ = "cms_entry_previews"



    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    entry_id: Mapped[int] = mapped_column(

        Integer, ForeignKey("cms_entries.id", ondelete="CASCADE"), nullable=False, index=True

    )

    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
