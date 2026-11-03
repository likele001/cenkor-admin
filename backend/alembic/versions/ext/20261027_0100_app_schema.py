"""占位迁移：app_schema_versions 已由公开链创建（方案 D）

本迁移最初在此处建表，后来确认该表属于平台核心、开源部署同样需要，
已前移到公开链的 20261014_124200_schema_versions。

保留本文件的原因：已部署环境的 alembic_version 指向本 revision，
删掉会报「未知 revision」。upgrade 为空实现，对任何环境都无副作用：
  - 新装：公开链已建表，走到这里跳过
  - 已部署：早已执行过，不会重跑

之所以留在闭源链尾（而不进公开链）：它的父节点 0029_product_commerce
属于闭源迁移，公开仓库看不到它。

Revision ID: 20261027_0100_app_schema
Revises: 20261007_0029_product_commerce
Create Date: 2026-10-27 16:00
"""
revision = "20261027_0100_app_schema"
down_revision = "20261007_0029_product_commerce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    return


def downgrade() -> None:
    return
