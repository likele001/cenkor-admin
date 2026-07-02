"""content engine + portal users + custom_fields

Revision ID: 20260610_0001_content_engine
Revises: 20260608_0002_apikey
Create Date: 2026-06-10 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260610_0001_content_engine"
down_revision: str | Sequence[str] | None = "20260608_0002_apikey"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- cms_content_types ----
    op.create_table(
        "cms_content_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(60), unique=True, nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(20), nullable=True),
        sa.Column("supports_category", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("supports_tags", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("default_list_template", sa.Text(), nullable=True),
        sa.Column("default_detail_template", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ---- cms_field_groups ----
    op.create_table(
        "cms_field_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_type_id", sa.Integer(), sa.ForeignKey("cms_content_types.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("icon", sa.String(20), nullable=True),
        sa.UniqueConstraint("content_type_id", "key", name="uq_field_group_ct_key"),
    )

    # ---- cms_field_definitions ----
    op.create_table(
        "cms_field_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_type_id", sa.Integer(), sa.ForeignKey("cms_content_types.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_key", sa.String(80), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("field_type", sa.String(20), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_value", sa.Text(), nullable=True),
        sa.Column("options", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("validation", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("cms_field_groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("content_type_id", "field_key", name="uq_field_def_ct_key"),
    )

    # ---- cms_field_options ----
    op.create_table(
        "cms_field_options",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("definition_id", sa.Integer(), sa.ForeignKey("cms_field_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("value", sa.String(80), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
    )

    # ---- cms_categories ----
    op.create_table(
        "cms_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_type_id", sa.Integer(), sa.ForeignKey("cms_content_types.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("cms_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("icon", sa.String(20), nullable=True),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("content_type_id", "slug", name="uq_category_ct_slug"),
    )
    op.create_index("ix_cms_categories_ct_parent", "cms_categories", ["content_type_id", "parent_id"])

    # ---- cms_tags ----
    op.create_table(
        "cms_tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_type_id", sa.Integer(), sa.ForeignKey("cms_content_types.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("color", sa.String(20), nullable=True),
        sa.UniqueConstraint("content_type_id", "slug", name="uq_tag_ct_slug"),
    )

    # ---- cms_content_tags ----
    op.create_table(
        "cms_content_tags",
        sa.Column("content_type_id", sa.Integer(), primary_key=True),
        sa.Column("content_id", sa.Integer(), primary_key=True),
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("cms_tags.id", ondelete="CASCADE"), primary_key=True),
    )

    # ---- cms_entries ----
    op.create_table(
        "cms_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_type_id", sa.Integer(), sa.ForeignKey("cms_content_types.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("slug", sa.String(120), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default="{}"),
        sa.Column("custom_fields", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default="{}"),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("cms_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("author_id", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("content_type_id", "slug", name="uq_entry_ct_slug"),
    )
    op.create_index("ix_cms_entries_ct_status", "cms_entries", ["content_type_id", "status"])
    op.create_index("ix_cms_entries_status", "cms_entries", ["status"])
    op.create_index("ix_cms_entries_custom_fields", "cms_entries", ["custom_fields"], postgresql_using="gin")

    # ---- portal_users ----
    op.create_table(
        "portal_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(80), unique=True, nullable=False),
        sa.Column("email", sa.String(120), unique=True, nullable=True),
        sa.Column("phone", sa.String(20), unique=True, nullable=True),
        sa.Column("nickname", sa.String(80), nullable=False, server_default=""),
        sa.Column("avatar", sa.String(500), nullable=True),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_ip", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_portal_users_username"), "portal_users", ["username"], unique=True)
    op.create_index(op.f("ix_portal_users_email"), "portal_users", ["email"], unique=True)
    op.create_index(op.f("ix_portal_users_phone"), "portal_users", ["phone"], unique=True)

    # ---- portal_user_oauth ----
    op.create_table(
        "portal_user_oauth",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("portal_users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("provider", sa.String(40), nullable=False, index=True),
        sa.Column("open_id", sa.String(200), nullable=False),
        sa.Column("union_id", sa.String(200), nullable=True),
        sa.Column("access_token_enc", sa.String(500), nullable=True),
        sa.Column("refresh_token_enc", sa.String(500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "open_id", name="uq_portal_oauth_provider_openid"),
    )

    # ---- portal_login_logs ----
    op.create_table(
        "portal_login_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("portal_users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("provider", sa.String(40), nullable=False, server_default="local"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )

    # ---- 现有表扩展 ----
    op.add_column("cms_products", sa.Column("custom_fields", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default="{}"))
    op.add_column("cms_cases", sa.Column("custom_fields", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default="{}"))
    op.add_column("cms_news", sa.Column("custom_fields", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False, server_default="{}"))
    op.add_column("auth_users", sa.Column("user_type", sa.String(20), nullable=False, server_default="admin"))

    # ---- 种子数据：默认内容类型 ----
    op.execute(
        "INSERT INTO cms_content_types (key, name, description, icon, supports_category, supports_tags) VALUES "
        "('product', '产品', '公司产品管理', '📦', true, true), "
        "('case', '案例', '客户案例', '📋', true, false), "
        "('news', '新闻', '新闻/博客', '📰', true, true) "
        "ON CONFLICT (key) DO NOTHING"
    )

    # ---- 种子数据：默认字段分组 ----
    op.execute(
        "INSERT INTO cms_field_groups (content_type_id, key, label, sort) VALUES "
        "((SELECT id FROM cms_content_types WHERE key='product'), 'basic', '基础信息', 0), "
        "((SELECT id FROM cms_content_types WHERE key='product'), 'specs', '技术规格', 1), "
        "((SELECT id FROM cms_content_types WHERE key='case'), 'basic', '基础信息', 0), "
        "((SELECT id FROM cms_content_types WHERE key='news'), 'basic', '基础信息', 0) "
        "ON CONFLICT (content_type_id, key) DO NOTHING"
    )

    # ---- 种子数据：默认字段定义 ----
    op.execute(
        "INSERT INTO cms_field_definitions (content_type_id, field_key, label, field_type, required, sort, group_id) VALUES "
        "((SELECT id FROM cms_content_types WHERE key='product'), 'price', '价格', 'number', false, 0, (SELECT id FROM cms_field_groups WHERE content_type_id=(SELECT id FROM cms_content_types WHERE key='product') AND key='specs')), "
        "((SELECT id FROM cms_content_types WHERE key='product'), 'screenshots', '产品截图', 'images', false, 1, (SELECT id FROM cms_field_groups WHERE content_type_id=(SELECT id FROM cms_content_types WHERE key='product') AND key='specs')), "
        "((SELECT id FROM cms_content_types WHERE key='product'), 'docs_url', '文档地址', 'url', false, 2, (SELECT id FROM cms_field_groups WHERE content_type_id=(SELECT id FROM cms_content_types WHERE key='product') AND key='specs')), "
        "((SELECT id FROM cms_content_types WHERE key='case'), 'client_name', '客户名称', 'text', false, 0, (SELECT id FROM cms_field_groups WHERE content_type_id=(SELECT id FROM cms_content_types WHERE key='case') AND key='basic')), "
        "((SELECT id FROM cms_content_types WHERE key='case'), 'project_scale', '项目规模', 'select', false, 1, (SELECT id FROM cms_field_groups WHERE content_type_id=(SELECT id FROM cms_content_types WHERE key='case') AND key='basic')), "
        "((SELECT id FROM cms_content_types WHERE key='news'), 'source', '来源', 'text', false, 0, (SELECT id FROM cms_field_groups WHERE content_type_id=(SELECT id FROM cms_content_types WHERE key='news') AND key='basic')), "
        "((SELECT id FROM cms_content_types WHERE key='news'), 'cover', '封面图', 'image', false, 1, (SELECT id FROM cms_field_groups WHERE content_type_id=(SELECT id FROM cms_content_types WHERE key='news') AND key='basic')) "
        "ON CONFLICT (content_type_id, field_key) DO NOTHING"
    )

    # ---- 新增权限 ----
    op.execute(
        "INSERT INTO rbac_permissions (code, type, name) VALUES "
        "('cms:content_types:read', 'API', '查看内容类型'), "
        "('cms:content_types:write', 'API', '管理内容类型'), "
        "('cms:field_definitions:read', 'API', '查看字段定义'), "
        "('cms:field_definitions:write', 'API', '管理字段定义'), "
        "('cms:categories:read', 'API', '查看分类'), "
        "('cms:categories:write', 'API', '管理分类'), "
        "('cms:tags:read', 'API', '查看标签'), "
        "('cms:tags:write', 'API', '管理标签'), "
        "('cms:entries:read', 'API', '查看通用内容'), "
        "('cms:entries:write', 'API', '管理通用内容'), "
        "('portal:users:read', 'API', '查看前台用户'), "
        "('portal:users:write', 'API', '管理前台用户') "
        "ON CONFLICT (code) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM rbac_permissions WHERE code IN ("
        "'cms:content_types:read', 'cms:content_types:write', "
        "'cms:field_definitions:read', 'cms:field_definitions:write', "
        "'cms:categories:read', 'cms:categories:write', "
        "'cms:tags:read', 'cms:tags:write', "
        "'cms:entries:read', 'cms:entries:write', "
        "'portal:users:read', 'portal:users:write')"
    )
    op.drop_column("auth_users", "user_type")
    op.drop_column("cms_news", "custom_fields")
    op.drop_column("cms_cases", "custom_fields")
    op.drop_column("cms_products", "custom_fields")
    op.drop_table("portal_login_logs")
    op.drop_table("portal_user_oauth")
    op.drop_table("portal_users")
    op.drop_table("cms_entries")
    op.drop_table("cms_content_tags")
    op.drop_table("cms_tags")
    op.drop_table("cms_categories")
    op.drop_table("cms_field_options")
    op.drop_table("cms_field_definitions")
    op.drop_table("cms_field_groups")
    op.drop_table("cms_content_types")
