"""add_seo_columns_to_content

Revision ID: 20260806_2000
Revises: 043ba4506897
Create Date: 2026-08-06 20:00:00.000000
"""
from collections.abc import Sequence

from alembic import op


revision: str = "20260806_2000"
down_revision: str | Sequence[str] | None = "043ba4506897"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 给三类内容都加 SEO 三列（每条记录可独立覆盖站点默认 meta）
    for table in ("cms_products", "cms_cases", "cms_news"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS seo_title varchar(200)")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS seo_description text")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS seo_keywords varchar(500)")

    # 顺手清掉我之前测试时塞进 cms_products.custom_fields 的 SEO 测试数据
    # （保留用户真实的非 SEO 自定义字段）
    op.execute("""
        UPDATE cms_products
        SET custom_fields = custom_fields - 'seo_title' - 'seo_description' - 'seo_keywords'
        WHERE custom_fields ? 'seo_title'
           OR custom_fields ? 'seo_description'
           OR custom_fields ? 'seo_keywords'
    """)


def downgrade() -> None:
    for table in ("cms_products", "cms_cases", "cms_news"):
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS seo_keywords")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS seo_description")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS seo_title")
