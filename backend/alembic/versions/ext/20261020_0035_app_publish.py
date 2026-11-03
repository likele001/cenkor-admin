"""app_submissions：上架/撤回 + manifest v2 契约快照

审核与上架分离：审核只判「内容合规」，上架（publish）才让包对外可见/可下载，
撤回（yank）只阻止新下载，已装实例不受影响。为此新增：

- schema_version      manifest v2 的数据契约版本（整数，缺省 NULL = v1 存量包）
- min_core_version    宿主最低版本（semver 字符串）
- changelog           本版更新日志，门户详情页/实例更新弹窗展示
- published_at        上架时间；NULL = 审核通过但未上架（不对外）
- yanked_at           撤回上架时间；非 NULL 即不再对外分发

存量兼容：老行 published_at 仍为 NULL，但 status 已是 approved/installed，
公开目录按「approved/installed 且未撤回」放行（见 is_published），因此不影响现有目录。
纯加列、均可空，可安全回滚。

2026-10-30 说明
--------------
本迁移曾因「库结构比 alembic_version 新」而被反复重跑，撞
DuplicateColumn: column "schema_version" of relation "app_submissions" already exists。

现在 DDL 幂等由统一层负责（core/migration_idempotent.py，在 alembic/env.py 里装），
「已存在就跳过」对所有迁移统一生效，不需要在每个迁移里各写一遍 ——
本项目的迁移图是 6 条链交织（core/erp/crm/mes/commerce/ext），逐个改迁移
既治标又容易漏。详见 core/migration_idempotent.py。

本文件因此保持原貌，只把建索引改成 if_not_exists（alembic 1.12+ 原生支持），
其余逻辑一字未动。

Revision ID: 20261020_0035_app_publish
Revises: 20261018_0034_upgrade_notes
Create Date: 2026-10-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20261020_0035_app_publish"
# 闭源链根：顺延到公开链新 head（当前 cms_templates 挂在 ai_video_jobs 之后），
# 否则本地全量视角会出现两个 head（公开链一支、闭源链一支）。此文件被 .gitignore 排除，
# 改这里不影响公开仓库。
down_revision = "20261031_1600_cms_permalink"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_submissions", sa.Column("schema_version", sa.Integer(), nullable=True))
    op.add_column(
        "app_submissions", sa.Column("min_core_version", sa.String(length=20), nullable=True)
    )
    op.add_column("app_submissions", sa.Column("changelog", sa.Text(), nullable=True))
    op.add_column(
        "app_submissions",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "app_submissions",
        sa.Column("yanked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_app_submissions_published_at",
        "app_submissions",
        ["published_at"],
        if_not_exists=True,
    )
    # 存量已过审的行补一个上架时间，语义上等价于「此前一直对外分发」。
    op.execute(
        "UPDATE app_submissions SET published_at = COALESCE(reviewed_at, created_at) "
        "WHERE status IN ('approved', 'installed') AND published_at IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_app_submissions_published_at", table_name="app_submissions", if_exists=True)
    op.drop_column("app_submissions", "yanked_at")
    op.drop_column("app_submissions", "published_at")
    op.drop_column("app_submissions", "changelog")
    op.drop_column("app_submissions", "min_core_version")
    op.drop_column("app_submissions", "schema_version")
