"""CMS 伪静态 URL 规则字段

给三级 URL 配置留位置，全部 nullable 且默认空：

    cms_categories.url_pattern   栏目级规则，留空继承站点默认
    cms_tags.url_pattern         标签级规则，留空继承站点默认
    cms_entries.url_path         单条内容手填的完整路径，留空按规则生成

默认值全部为空 = 走 ``apps/cms/permalink.py`` 的 DEFAULT_PATTERNS，
生成结果与改造前线上地址完全一致（``/article/x.html`` / ``/category/mes/``），
所以这次迁移不改变任何现有 URL，也不需要回填数据。

**为什么挂在 20261031_1310_cms_ai_tables**
必须是**公开链**上的节点。20261027_0100_app_schema 属闭源模块，
被 .gitignore 排除（第 172 行），公开仓库里不存在 —— 挂上去会让 clone 后
的 `alembic upgrade head` 直接报「Can't locate revision identified by
'20261027_0100_app_schema'」，公开视角的迁移图也会断链
（`scripts/check-migration-graph.py --tracked-only` 会拦下提交）。

闭源链上原本挂在 20261031_1310_cms_ai_tables 后面的 20261020_0035_app_publish
已顺延改挂到本迁移，本地全量链仍保持单 head。

库里 ``alembic_version`` 之前是 20261027_0100_app_schema，跨链升级需要
先 ``alembic stamp 20261031_1310_cms_ai_tables``，否则 alembic 会尝试
从 app_schema 找起点。本迁移本身幂等（列已存在就跳过），重复执行安全。

**为什么要唯一索引**
手填的 url_path 决定磁盘上「哪个地址指向谁」，两条内容填同一个路径就是
静默互相覆盖 —— 页面还能开，但内容对不上号。应用层保存前会先查重给友好提示，
索引作为并发下的兜底。PostgreSQL 唯一索引允许多个 NULL，未手填的内容互不影响。

Revision ID: 20261031_1600_cms_permalink
Revises: 20261031_1310_cms_ai_tables
Create Date: 2026-10-31 16:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261031_1600_cms_permalink"
down_revision: str | Sequence[str] | None = "20261031_1310_cms_ai_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cms_categories",
        sa.Column("url_pattern", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "cms_tags",
        sa.Column("url_pattern", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "cms_entries",
        sa.Column("url_path", sa.String(length=300), nullable=True),
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_entries_site_url_path "
        "ON cms_entries (site_id, url_path)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_cms_entries_site_url_path")
    op.drop_column("cms_entries", "url_path")
    op.drop_column("cms_tags", "url_pattern")
    op.drop_column("cms_categories", "url_pattern")
