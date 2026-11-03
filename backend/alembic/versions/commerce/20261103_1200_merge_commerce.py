"""合流点：公开链两条并行分支合并于此，commerce 段改挂到它之后

revision: 20261103_1200_merge_commerce
down_revision: (20261103_1100_cms_orphan, 20261020_0035_app_publish)

背景（v0.5.11 支付中心 / 生态交易层开源时的迁移图整理）

payment 与 commerce 此前闭源，迁移挂在闭源链中间：
    mes_0009 → commerce_0020 → payment_0021 → … → cloud_0025 → workflow_0027
    → product_commerce_0029 → app_schema_0100
开源后这些迁移要进公开仓库，但有两个父节点拿不到：
    · 20260922_0020_commerce.down        = 20260904_mes_0009   （ERP→CRM→MES 闭源链尾）
    · 20261007_0029_product_commerce.down = 20260925_0027_workflow（workflow 仍闭源）
父节点不在公开仓库 → 公开视图断链 + 多 head，`alembic upgrade head` 直接失败。

修法：只做合流，不改任何挂载对象的连接关系。

    20261031_1600_cms_permalink
      ├→ 20261102_1210 → … → 20261103_1100_cms_orphan ─┐
      └→ 20261020_0035_app_publish ────────────────────┴→ 本迁移
                                                          ↓
                                                     20260922_0020_commerce
                                                          ↓
                                                     … → 20261027_0100_app_schema

为什么不能把 commerce_0020 直接挂到公开链尾
------------------------------------------
那会切断 erp/crm/mes 与主链的连接，它们变成「未应用分支」，
    `upgrade heads` 会把 ERP 全部迁移重跑一遍，撞 DuplicateTable。
合流方案下，已部署环境（version 表指向 collect 链尾与 cms_orphan）
的祖先闭包仍然覆盖全部节点，`upgrade heads` 为**空操作**。

upgrade / downgrade 均为空实现：本迁移只表达图结构，不触碰任何表。
"""
from __future__ import annotations

revision = "20261103_1200_merge_commerce"
down_revision = ("20261103_1100_cms_orphan", "20261020_0035_app_publish")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """只做图合流，无 DDL。"""


def downgrade() -> None:
    """只做图合流，无 DDL。"""
