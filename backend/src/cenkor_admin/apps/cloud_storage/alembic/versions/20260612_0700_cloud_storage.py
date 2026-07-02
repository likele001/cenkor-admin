"""create cloud_storage_config and migration_jobs

Revision ID: 20260612_0700
Revises: 20260612_0600
Create Date: 2026-06-12 07:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "20260612_0700"
down_revision = "20260612_0600"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cloud_storage_config",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("active_provider", sa.String(20), server_default="tencent"),
        sa.Column("creds_tencent", sa.Text, nullable=True),
        sa.Column("creds_aliyun", sa.Text, nullable=True),
        sa.Column("creds_qiniu", sa.Text, nullable=True),
        sa.Column("creds_upyun", sa.Text, nullable=True),
        sa.Column("updated_by", sa.Integer, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "cloud_storage_migration_jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String(20), server_default="minio"),
        sa.Column("target", sa.String(20), nullable=False),
        sa.Column("total", sa.Integer, server_default="0"),
        sa.Column("done", sa.Integer, server_default="0"),
        sa.Column("failed", sa.Integer, server_default="0"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("cloud_storage_migration_jobs")
    op.drop_table("cloud_storage_config")
