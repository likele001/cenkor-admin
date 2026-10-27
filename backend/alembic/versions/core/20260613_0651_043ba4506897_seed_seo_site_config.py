"""seed_seo_site_config

Revision ID: 043ba4506897
Revises: 20260612_0700
Create Date: 2026-06-13 06:51:28.046826
"""
from collections.abc import Sequence

from alembic import op


revision: str = '043ba4506897'
down_revision: str | Sequence[str] | None = '20260612_0700'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO cms_site_config (key, value, description, updated_at) VALUES
        ('seo.default_title', '"LightMes · 中小加工厂生产管理系统 · 源码交付私有部署"', '全站默认标题（Product 未设置 seo_title 时使用）', now()),
        ('seo.default_description', '"专为中小加工厂打造的轻量化 MES 系统。扫码报工、计件工资自动算、CRM 客户管理、AI 工厂助手、仓储库存、质量溯源。源码部署在自己服务器，数据不出厂。免费社区版开源下载。"', '全站默认 meta description', now()),
        ('seo.default_keywords', '"MES系统,生产管理系统,扫码报工,计件工资,加工厂管理软件,私有部署,源码交付,中小企业MES,车间管理系统,工厂数字化"', '全站默认 meta keywords', now()),
        ('seo.og_image', '""', 'Open Graph 分享图 URL（1200×630 PNG）', now()),
        ('brand.name', '"辰科"', '站点品牌名', now()),
        ('brand.name_en', '"Cenkor"', '站点英文品牌名', now()),
        ('brand.tagline', '"让企业软件 更简单 更智能"', '站点口号', now())
        ON CONFLICT (key) DO UPDATE SET
            value = EXCLUDED.value,
            description = EXCLUDED.description,
            updated_at = now()
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM cms_site_config WHERE key IN (
            'seo.default_title', 'seo.default_description', 'seo.default_keywords',
            'seo.og_image',
            'brand.name', 'brand.name_en', 'brand.tagline'
        )
    """)
