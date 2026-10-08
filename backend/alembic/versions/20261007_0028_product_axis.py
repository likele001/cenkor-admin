"""product axis: 多产品/宿主维度 + app_key 命名空间

统一门户 hub（portal.cenkor.cn / admin.cenkor.cn）要同时服务 cenkormes / lightmes /
cenkor-admin 等多条产品线，必须给交易与制品模型加「目标产品」维度做目录隔离，
并把 app_key 的唯一性从全局升级为 (product, app_key) 命名空间，避免跨产品同名 key 撞车。

- app_submissions  加 product；唯一约束 (app_key, version) → (product, app_key, version)
- app_pricing      加 product；app_key 唯一索引 → (product, app_key) 唯一约束
- app_orders / app_licenses  加 product（交易/授权按产品归属，便于过滤与对账）
- cloud_device_codes / cloud_instances  加 product（实例绑定时上报所属产品）

存量数据全部是平台自营应用，回填 product='cenkor-admin'（server_default 兜底），
无跨产品冲突。所有加列均 NOT NULL + server_default，可安全回滚。

Revision ID: 20261007_0028_product_axis
Revises: 20260925_0027_workflow
Create Date: 2026-10-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261007_0028_product_axis"
down_revision = "20260925_0027_workflow"
branch_labels = None
depends_on = None

DEFAULT_PRODUCT = "cenkor-admin"


def upgrade() -> None:
    # ---------- app_submissions ----------
    op.add_column(
        "app_submissions",
        sa.Column("product", sa.String(length=32), nullable=False, server_default=DEFAULT_PRODUCT),
    )
    op.create_index("ix_app_submissions_product", "app_submissions", ["product"])
    op.drop_constraint("uq_app_submission_key_version", "app_submissions", type_="unique")
    op.create_unique_constraint(
        "uq_app_submission_product_key_version",
        "app_submissions",
        ["product", "app_key", "version"],
    )

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

    op.drop_constraint("uq_app_submission_product_key_version", "app_submissions", type_="unique")
    op.create_unique_constraint(
        "uq_app_submission_key_version", "app_submissions", ["app_key", "version"]
    )
    op.drop_index("ix_app_submissions_product", table_name="app_submissions")
    op.drop_column("app_submissions", "product")
