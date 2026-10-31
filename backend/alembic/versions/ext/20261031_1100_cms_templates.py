"""CMS 主题模板表（Jinja2）

一条记录 = 主题里的一个文件，渲染时 DB 优先、内置兜底，
用户只覆盖想改的文件即可，不必整包托管主题。

不在这里插入内置主题：内置模板跟代码走（apps/cms/builtin_theme.py），
代码升级即生效，也避免把几百行模板复制进迁移历史。

【链路位置：必须在公开链】
cms_templates 是平台核心表（主题定制属于开源能力），开源部署同样需要，
因此父节点取「公开仓库可见的链尾」20261029_1500_ai_video_jobs。

不能挂 20261027_0100_app_schema：该文件被 .gitignore 排除（第 169 行），
开源仓库里不存在，挂上去会让 clone 后的 `alembic upgrade head` 直接报
「Can't locate revision identified by '20261027_0100_app_schema'」。

闭源链的收口由 20261031_1200_cms_merge 负责：它以
(app_schema, cms_templates) 为双父做 merge，既保住已部署环境的
alembic_version 连续性，又让两条链各自单 head。

Revision ID: 20261031_1100_cms_templates   （27 字符，alembic_version 上限 32）
Revises: 20261029_1500_ai_video_jobs
Create Date: 2026-10-31 11:00

【为什么不对 cms_sites 建外键】
本条排在 cms_sites 之前（链上 ai_video_jobs → 本条 → 20261031_1300_cms_multisite），
建表时站点表还不存在，加 FK 会让 CREATE TABLE 直接失败（已用空库实测复现）。

跟随 cms_entries 的既有做法：建表只留 site_id 列 + 索引，
外键由后一条迁移统一补（见 20261031_1300_cms_multisite 里的 fk_cms_templates_site）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261031_1100_cms_templates"
down_revision: str | Sequence[str] | None = "20261029_1500_ai_video_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 幂等：已部署环境可能先由闭源链建过表，重跑不该炸
    if op.get_bind().execute(sa.text("select to_regclass('public.cms_templates')")).scalar():
        return

    op.create_table(
        "cms_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("theme", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="partial"),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("site_id", "theme", "path", name="uq_cms_templates_site_theme_path"),
    )
    op.create_index("ix_cms_templates_site_id", "cms_templates", ["site_id"])
    op.create_index("ix_cms_templates_site_theme", "cms_templates", ["site_id", "theme"])


def downgrade() -> None:
    # 索引随表一起删，IF EXISTS 保证重复降级不炸
    op.execute("DROP TABLE IF EXISTS cms_templates")
