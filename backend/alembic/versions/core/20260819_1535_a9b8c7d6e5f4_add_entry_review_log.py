"""add_entry_review_log

发布工作流（M2·P1 2.4）：cms_entry_review_log 审批记录表 + cms:entry:review 权限。

Revision ID: a9b8c7d6e5f4
Revises: d1e3f4a7b2c5
Create Date: 2026-08-19 15:35:00
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "a9b8c7d6e5f4"
down_revision: str | Sequence[str] | None = "d1e3f4a7b2c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cms_entry_review_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "entry_id", sa.Integer(),
            sa.ForeignKey("cms_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=True),
        sa.Column("reviewer_id", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_cms_entry_review_log_entry_id", "cms_entry_review_log", ["entry_id"])

    # 权限点种子（super_admin 始终通过；供普通角色在 RBAC 里分配）
    op.execute(
        "INSERT INTO rbac_permissions (code, type, name) "
        "SELECT 'cms:entry:review', 'api', '审批内容' "
        "WHERE NOT EXISTS (SELECT 1 FROM rbac_permissions WHERE code='cms:entry:review')"
    )


def downgrade() -> None:
    op.drop_index("ix_cms_entry_review_log_entry_id", table_name="cms_entry_review_log")
    op.drop_table("cms_entry_review_log")
    op.execute("DELETE FROM rbac_permissions WHERE code='cms:entry:review'")
