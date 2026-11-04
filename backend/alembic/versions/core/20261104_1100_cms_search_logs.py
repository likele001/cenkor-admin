"""站内搜索词日志

## 背景

选题缺口（topic_gap）此前只能从「已有内容」反推「缺什么」——那是模型的判断。
读者主动搜了什么、我们没搜到，才是可直接变选题的真实需求信号。
这张表就是那个信号源。

## 挂载位置

公开迁移，down_revision 必须指向**当前公开 head**（20261027_0100_app_schema）。
若用 autogenerate 默认值，它会挂在闭源的 20261103_1300_merge_closed 上，
开源版 `git clone` 后直接断链、一张表都建不出来。

执行用 `alembic upgrade heads`（全量图此刻会短暂出现 2 个 head，属正常中间态）。

Revision ID: 20261104_1100_cms_search_logs
Revises: 20261027_0100_app_schema
Create Date: 2026-11-04 11:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "20261104_1100_cms_search_logs"
down_revision: str | None = "20261027_0100_app_schema"
branch_labels: str | None = None
depends_on: str | None = None

_INDEXES = (
    ("ix_search_logs_norm_date", ["query_norm", "stat_date"]),
    ("ix_search_logs_stat_date", ["stat_date"]),
    ("ix_search_logs_site_date", ["site_id", "stat_date"]),
    ("ix_search_logs_result_date", ["result_count", "stat_date"]),
)


def upgrade() -> None:
    op.create_table(
        "cms_search_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("query", sa.String(200), nullable=False),
        sa.Column("query_norm", sa.String(200), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicked_entry_id", sa.Integer(), nullable=True),
        sa.Column("visitor_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("lang", sa.String(10), nullable=True),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, cols in _INDEXES:
        op.create_index(name, "cms_search_logs", cols)


def downgrade() -> None:
    for name, _cols in reversed(_INDEXES):
        op.drop_index(name, table_name="cms_search_logs")
    op.drop_table("cms_search_logs")
