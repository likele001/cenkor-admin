"""建站方案编排（cms_site_plans / cms_site_plan_items）

## 背景

需求清单要的是「一句话需求 → 栏目+选题 → 确认 → 自动产出」这条链，
原来只有零件（内容引擎、AI 批量），没有编排层，也没有「方案」这个中间态。
两张表就为这个中间态服务：方案先落库、人确认、再执行，避免模型输出直接
变成生产数据。

## 执行

`alembic upgrade heads`（down_revision 指向当前 head，链路保持单头）

## 前置条件：cms_sites 必须已存在

本表对 `cms_sites` 建了外键，而 `cms_sites` 由 `20261031_1300_cms_multisite`
创建。**在迁移图上 `cms_multisite` 是本条的历史祖先**，路径：

    multisite -> ai_tables -> permalink -> cat_url_tpl -> entry_links
    -> ai_missing -> sso_bindings -> cms_orphan -> merge_commerce
    -> ... -> app_schema -> cms_search_logs -> 本条

所以全新库按 `upgrade heads` 顺序执行，必然已满足前置条件。

但历史上 `merge_commerce` 曾被**追加** `cms_orphan` 作为第二个父节点，
已经越过 `merge_commerce` 的老库只改了版本戳、没有补跑 CMS 分支，
于是出现「版本号在 cms_sites 之后、库里却没有 cms_sites」的脏库。
这种库走到本条会抛 `UndefinedTable: relation "cms_sites" does not exist`，
报错位置离真实原因（版本戳失真）很远，排查成本高。

因此本条在建表前显式校验，缺失时抛可执行的诊断信息，而不是让 PG 的
原生错误冒上来。修复见 `scripts/repair-cms-branch.py`。

Revision ID: 20261127_1200_cms_site_plans
Revises: 20261104_1100_cms_search_logs
Create Date: 2026-11-27 12:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261127_1200_cms_site_plans"
down_revision: str | None = "20261104_1100_cms_search_logs"
branch_labels: str | None = None
depends_on: str | None = None


_MISSING_SITES_MSG = """\
[迁移 20261127_1200_cms_site_plans] 缺少前置表 cms_sites，无法创建 cms_site_plans。

原因：当前库的 alembic_version（{rev}）在迁移图上位于
      20261031_1300_cms_multisite 之后，但 CMS 分支的 DDL 从未真正执行过。
      这类库产生于 2026-11 merge_commerce 追加 cms_orphan 为第二父节点的
      历史遗留：老库只被改了版本戳，没有补跑分支。不是本条迁移的问题，
      也不是库本身坏了。

修复（任选其一）：
  A. 保留数据，补跑缺失的 CMS 分支，然后正常升级：
       python3 scripts/repair-cms-branch.py --db {dbname}
       alembic upgrade heads

  B. 纯开发库、数据可弃，直接重建：
       dropdb {dbname} && createdb {dbname} && alembic upgrade heads
"""


def _require_cms_sites() -> None:
    """cms_sites 缺失时给出可执行的诊断，而不是裸 UndefinedTable。"""
    bind = op.get_bind()
    if bind.execute(sa.text("select to_regclass('public.cms_sites')")).scalar():
        return
    rev = bind.execute(sa.text("select version_num from alembic_version")).scalars().all()
    dbname = bind.execute(sa.text("select current_database()")).scalar()
    raise RuntimeError(
        _MISSING_SITES_MSG.format(rev=", ".join(rev) or "(空)", dbname=dbname)
    )


def upgrade() -> None:
    _require_cms_sites()
    op.create_table(
        "cms_site_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "site_id",
            sa.Integer(),
            sa.ForeignKey("cms_sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("brief", postgresql.JSONB(), nullable=True),
        sa.Column("plan_json", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column(
            "content_type_id",
            sa.Integer(),
            sa.ForeignKey("cms_content_types.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("lang", sa.String(20), nullable=False, server_default="zh-CN"),
        sa.Column("batch_job_id", sa.Integer(), nullable=True),
        sa.Column("summary", sa.String(200), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("confirmed_by", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_cms_site_plans_site_id", "cms_site_plans", ["site_id"])
    op.create_index("ix_cms_site_plans_status", "cms_site_plans", ["status"])
    op.create_index("ix_site_plans_site_status", "cms_site_plans", ["site_id", "status"])

    op.create_table(
        "cms_site_plan_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("cms_site_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(16), nullable=False, server_default="category"),
        sa.Column("parent_key", sa.String(64), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_cms_site_plan_items_site_id", "cms_site_plan_items", ["site_id"])
    op.create_index("ix_site_plan_items_plan_seq", "cms_site_plan_items", ["plan_id", "seq"])
    op.create_index("ix_site_plan_items_plan_kind", "cms_site_plan_items", ["plan_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_site_plan_items_plan_kind", table_name="cms_site_plan_items")
    op.drop_index("ix_site_plan_items_plan_seq", table_name="cms_site_plan_items")
    op.drop_index("ix_cms_site_plan_items_site_id", table_name="cms_site_plan_items")
    op.drop_table("cms_site_plan_items")
    op.drop_index("ix_site_plans_site_status", table_name="cms_site_plans")
    op.drop_index("ix_cms_site_plans_status", table_name="cms_site_plans")
    op.drop_index("ix_cms_site_plans_site_id", table_name="cms_site_plans")
    op.drop_table("cms_site_plans")
