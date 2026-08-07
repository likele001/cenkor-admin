"""add keep_local_backup to cloud_storage_config

Revision ID: 20260807_1347
Revises: 20260806_2000
Create Date: 2026-08-07 13:47:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "20260807_1347"
down_revision = "20260806_2000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 开启后：上传到云存储的同时，服务端把对象回写一份到本地 MinIO 作备份
    op.add_column(
        "cloud_storage_config",
        sa.Column(
            "keep_local_backup",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("cloud_storage_config", "keep_local_backup")
