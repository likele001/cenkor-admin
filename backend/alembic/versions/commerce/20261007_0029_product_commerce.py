"""product axis（闭源部分）：commerce / cloud 表补 product 维度

接 20261007_0028_product_axis —— 那条只处理公开表 app_submissions，本条负责
其余由商业应用创建、不进公开仓库的表：

- app_pricing      加 product；app_key 唯一索引 → (product, app_key) 唯一约束
- app_orders / app_licenses  加 product（交易/授权按产品归属，便于过滤与对账）
- cloud_device_codes / cloud_instances  加 product（实例绑定时上报所属产品）

存量数据全部是平台自营应用，回填 product='cenkor-admin'（server_default 兜底），
无跨产品冲突。所有加列均 NOT NULL + server_default，可安全回滚。

# 挂载点说明：本迁移改的表由 20260922_0020_commerce / 20260924_0025_cloud 创建，
# 这两者自 v0.5.11 起随仓开源，因此本条也属公开链。
# 原先挂在 20260925_0027_workflow（workflow 仍闭源）之后，公开仓库拿不到父节点会断链，
# 现改挂 20260924_0025_cloud —— 它才是本迁移真正依赖的建表迁移。
Revision ID: 20261007_0029_product_commerce
Revises: 20260924_0025_cloud
Create Date: 2026-10-07
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261007_0029_product_commerce"
down_revision = "20260924_0025_cloud"
branch_labels = None
depends_on = None

DEFAULT_PRODUCT = "cenkor-admin"


def upgrade() -> None:
    # ---------- app_pricing ----------
    op.add_column(
        "app_pricing",
        sa.Column("product", sa.String(length=32), nullable=False, server_default=DEFAULT_PRODUCT),
    )
    op.create_index("ix_app_pricing_product", "app_pricing", ["product"])
    # 旧：app_key 上是唯一索引 ix_app_pricing_app_key（由 unique=True,index=True 生成）
    op.drop_index("ix_app_pricing_app_key", table_name="app_pricing")
    # 新：app_key 保留普通索引（model index=True），唯一性改由 (product, app_key) 约束保证
    op.create_index("ix_app_pricing_app_key", "app_pricing", ["app_key"])
    op.create_unique_constraint("uq_app_pricing_product_key", "app_pricing", ["product", "app_key"])

    # ---------- app_orders ----------
    op.add_column(
        "app_orders",
        sa.Column("product", sa.String(length=32), nullable=False, server_default=DEFAULT_PRODUCT),
    )
    op.create_index("ix_app_orders_product", "app_orders", ["product"])

    # ---------- app_licenses ----------
    op.add_column(
        "app_licenses",
        sa.Column("product", sa.String(length=32), nullable=False, server_default=DEFAULT_PRODUCT),
    )
    op.create_index("ix_app_licenses_product", "app_licenses", ["product"])

    # ---------- cloud_device_codes ----------
    op.add_column(
        "cloud_device_codes",
        sa.Column("product", sa.String(length=32), nullable=False, server_default=DEFAULT_PRODUCT),
    )
    op.create_index("ix_cloud_device_codes_product", "cloud_device_codes", ["product"])

    # ---------- cloud_instances ----------
    op.add_column(
        "cloud_instances",
        sa.Column("product", sa.String(length=32), nullable=False, server_default=DEFAULT_PRODUCT),
    )
    op.create_index("ix_cloud_instances_product", "cloud_instances", ["product"])


def downgrade() -> None:
    op.drop_index("ix_cloud_instances_product", table_name="cloud_instances")
    op.drop_column("cloud_instances", "product")

    op.drop_index("ix_cloud_device_codes_product", table_name="cloud_device_codes")
    op.drop_column("cloud_device_codes", "product")

    op.drop_index("ix_app_licenses_product", table_name="app_licenses")
    op.drop_column("app_licenses", "product")

    op.drop_index("ix_app_orders_product", table_name="app_orders")
    op.drop_column("app_orders", "product")

    op.drop_constraint("uq_app_pricing_product_key", "app_pricing", type_="unique")
    op.drop_index("ix_app_pricing_app_key", table_name="app_pricing")
    op.create_index("ix_app_pricing_app_key", "app_pricing", ["app_key"], unique=True)
    op.drop_index("ix_app_pricing_product", table_name="app_pricing")
    op.drop_column("app_pricing", "product")
