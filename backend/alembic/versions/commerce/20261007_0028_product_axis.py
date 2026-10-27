"""product axis（公开部分）：app_submissions 多产品维度 + app_key 命名空间

统一门户 hub（portal.cenkor.cn / admin.cenkor.cn）要同时服务 cenkormes / lightmes /
cenkor-admin 等多条产品线，必须给交易与制品模型加「目标产品」维度做目录隔离，
并把 app_key 的唯一性从全局升级为 (product, app_key) 命名空间，避免跨产品同名 key 撞车。

本迁移只处理【公开表】：
- app_submissions  加 product；唯一约束 (app_key, version) → (product, app_key, version)

其余（app_pricing / app_orders / app_licenses / cloud_device_codes / cloud_instances）由闭源
迁移 20261007_0029_product_commerce 接续，因为那些表由商业 commerce / cloud 迁移创建，
公开仓库里不存在。

存量数据全部是平台自营应用，回填 product='cenkor-admin'（server_default 兜底），
无跨产品冲突。所有加列均 NOT NULL + server_default，可安全回滚。

# 挂载点说明：本迁移只依赖公开表 app_submissions（由 20260611_1500_app_store 创建），
# 因此挂在【公开链 head】20260925_0026_app_enabled 上。切勿改挂到 20260925_0027_workflow ——
# 那属于闭源链，不进公开仓库，挂进去会让 clone 出来的实例在 alembic upgrade head
# 时报 KeyError，数据库一张表都建不出来（闭源链整体已顺延挂到本迁移之后）。
Revision ID: 20261007_0028_product_axis
Revises: 20260925_0026_app_enabled
Create Date: 2026-10-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261007_0028_product_axis"
down_revision = "20260925_0026_app_enabled"
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


def downgrade() -> None:
    op.drop_constraint("uq_app_submission_product_key_version", "app_submissions", type_="unique")
    op.create_unique_constraint(
        "uq_app_submission_key_version", "app_submissions", ["app_key", "version"]
    )
    op.drop_index("ix_app_submissions_product", table_name="app_submissions")
    op.drop_column("app_submissions", "product")
