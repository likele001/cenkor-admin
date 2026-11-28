"""通知网关：mon_channels 原地扩展 + notify_outbox

Revision ID: 20261128_1200_notify
Revises: 20261127_1500_monitor
Create Date: 2026-11-28 12:00

设计要点
--------
1. 表名不动的原地扩展。巡检在用的 ``mon_channels`` 保留表名，逻辑上升级为
   通用通知渠道（代码里可把模型类改名为 NotifyChannel，``__tablename__``
   仍指向 ``mon_channels``）。只加列/放宽长度，老代码完全兼容，不需要停服
   窗口，也不需要先迁移还是先发代码的硬顺序。
   - ``kind`` 放宽到 24 字符，容纳 wecom_app / wecom_robot / feishu_robot /
     dingtalk_robot；``extra`` 继续存 corpid / agentid / 收件人等非敏感配置，
     ``secret`` 继续存加密后的 webhook 地址或应用 secret。
   - 新增 ``events`` 订阅过滤：NULL = 订阅全部事件（老巡检通道行为不变），
     数组 = 只订阅列出的 event，避免把审核消息推到运维群。
2. 新增 ``notify_outbox``：一个事件 x 一个渠道一行，发送失败由现有
   ``scheduler.tick``（30s）重试，attempts 到 3 置 failed；不引 Celery。
3. 表名保留 ``mon_channels`` 是刻意的：rename 会造成「迁移完成、旧代码还在跑
   就查不到表」的切换窗口。等渠道模型稳定后再单独做一次 rename 迁移。

上线顺序
--------
``alembic upgrade heads`` 与后端代码可任意先后（纯增量变更）。代码侧需同步：

- ``apps/monitor/models.py::MonChannel``：保留 __tablename__，补 events 字段
  （或新增 NotifyChannel 复用同名表）
- ``apps/monitor/service.py::_send`` 切到 ``notify_service``
- 新增 ``apps/notification/notify_service.py`` 与 outbox 消费钩子
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261128_1200_notify"
# 挂公开 head 而非闭源的 20261127_1500_monitor：
# 公开仓库里 monitor 迁移不存在（apps/monitor 闭源，文件被 .gitignore 排除），
# 依赖它会让 clone 下来的人 alembic 直接 KeyError，且公开视图出现双 head。
down_revision: str | None = "20261127_1700_cms_ab"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ---- 1. 渠道表原地扩展 ----
    # wecom_robot=11 / feishu_robot=12 / dingtalk_robot=14 / wecom_app=9，
    # 原来的 16 不够留给后续 kind，统一放宽到 24。
    op.alter_column(
        "mon_channels",
        "kind",
        existing_type=sa.String(16),
        type_=sa.String(24),
        existing_nullable=False,
        existing_server_default="wecom",
    )

    # NULL = 全部事件；数组 = 只订阅列出的 event。
    op.add_column(
        "mon_channels",
        sa.Column("events", postgresql.JSONB(), nullable=True),
    )

    # ---- 2. 发送 outbox ----
    op.create_table(
        "notify_outbox",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=True),
        sa.Column(
            "channel_id",
            sa.Integer(),
            sa.ForeignKey("mon_channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # pending / sending / sent / skipped / failed
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notify_outbox_site_id", "notify_outbox", ["site_id"])
    op.create_index("ix_notify_outbox_channel_id", "notify_outbox", ["channel_id"])
    # 消费查询：status='pending' AND next_retry_at <= now()
    op.create_index(
        "ix_notify_outbox_status_retry", "notify_outbox", ["status", "next_retry_at"]
    )
    op.create_index("ix_notify_outbox_event_created", "notify_outbox", ["event", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_notify_outbox_event_created", table_name="notify_outbox")
    op.drop_index("ix_notify_outbox_status_retry", table_name="notify_outbox")
    op.drop_index("ix_notify_outbox_channel_id", table_name="notify_outbox")
    op.drop_index("ix_notify_outbox_site_id", table_name="notify_outbox")
    op.drop_table("notify_outbox")

    op.drop_column("mon_channels", "events")
    # 注意：若已存在长度 > 16 的 kind，downgrade 会失败，这是预期行为。
    op.alter_column(
        "mon_channels",
        "kind",
        existing_type=sa.String(24),
        type_=sa.String(16),
        existing_nullable=False,
        existing_server_default="wecom",
    )