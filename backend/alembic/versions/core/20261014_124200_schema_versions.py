"""app_schema_versions 记账表（公开链）

应用自带 schema 机制（方案 D）的版本账本：记录每个应用 schema.sql 的
version + checksum，内容没变就整段跳过，避免每次启动都跑 DDL。

**必须放在公开链**：这套机制属于平台核心，开源部署同样需要
（core/app_schema.py 直接依赖本表）。位置紧接公开 head gen_inventory，
闭源链的挂载点 0035_app_publish 顺延到本迁移之后。

Revision ID: 20261014_124200_schema_versions   （31 字符，alembic_version 上限 32）
Revises: 20261014_124126_gen_inventory
"""
from alembic import op

revision = "20261014_124200_schema_versions"
down_revision = "20261014_124126_gen_inventory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS app_schema_versions (
            app_key    VARCHAR(64) PRIMARY KEY,
            version    VARCHAR(32) NOT NULL,
            checksum   VARCHAR(64) NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app_schema_versions")
