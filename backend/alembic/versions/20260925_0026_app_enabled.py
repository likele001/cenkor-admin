"""平台应用启用/停用：platform_apps.enabled

revision: 20260925_0026_app_enabled
down_revision: 20260924_0025_cloud

背景：应用中心此前只有「安装 / 卸载」两态 —— 卸载会清掉菜单、权限授权与
注册的内容数据，代价过高；而实际运营中大量场景只是「暂时不想用」（如换季停
用某个业务应用、排障时先摘掉可疑应用），需要一种可逆的软停用。

设计要点：
1. ``enabled`` 与 ``status`` 正交：status 表达「装没装」，enabled 表达「开没开」。
   不新增枚举值，避免影响既有 status 判断（商店取数、needs_upgrade 计算等）。
2. server_default=true —— 存量 12 个应用升级后全部自动启用，行为与升级前一致。
3. 停用不改菜单行、不删角色授权：菜单 ``status`` 置 disabled 即可让
   ``_build_user_brief`` 过滤掉，启用时原样恢复，无损。
4. 本迁移只新增一列，不触碰任何既有列与数据；downgrade 直接删列。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260925_0026_app_enabled"
down_revision = "20260924_0025_cloud"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_apps",
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="应用启用状态：false=已停用（菜单隐藏 + API 门禁），数据保留",
        ),
    )
    op.create_index(
        "ix_platform_apps_enabled", "platform_apps", ["enabled"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_platform_apps_enabled", table_name="platform_apps")
    op.drop_column("platform_apps", "enabled")
