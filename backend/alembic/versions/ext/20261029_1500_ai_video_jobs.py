"""AI 视频生成任务表

视频和图片的根本差别是「不是一次请求一次结果」：提交拿到 task_id，
再轮询 60~300 秒才有产物，且产物 URL 只有约 24 小时有效期。所以需要
一张表持久化任务状态 —— 进程重启、页面关闭都不能让任务和已花的钱失联。

同时补两件事：
1. 封面图字段（cover_media_id）：og:image 只能是图片，视频必须抽首帧。
2. 单价表放开 kind='video' 的口径（表结构不变，只是把注释里允许的取值
   从 chat/embedding/image 扩到含 video，unit 取 'video' 按条计价）。

Revision ID: 20261029_1500_ai_video_jobs
Revises: 20261014_124200_schema_versions
Create Date: 2026-10-29 15:00

为什么挂在 schema_versions（公开链 head）而不是 app_schema：
app_schema 属闭源模块，被 .gitignore 排除，公开仓库看不到它 —— 挂在它后面
会让公开视角直接断链（`check-migration-graph.py --tracked-only` 会拦下）。
闭源链根 0035_app_publish 已顺延改挂到本迁移，本地全量链仍是单 head。
本地库若已应用过 app_schema，需先 `alembic stamp head` 再继续升级。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261029_1500_ai_video_jobs"
down_revision: str | Sequence[str] | None = "20261014_124200_schema_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cms_ai_video_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("entry_id", sa.Integer(), nullable=True),
        sa.Column("mode", sa.String(length=8), nullable=False, server_default="t2v"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("provider_task_id", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_media_id", sa.Integer(), nullable=True),
        sa.Column("media_id", sa.Integer(), nullable=True),
        sa.Column("cover_media_id", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("upstream_url", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        # SET NULL 而不是 CASCADE：条目被删掉后任务记录仍要留着做成本审计
        sa.ForeignKeyConstraint(["entry_id"], ["cms_entries.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_media_id"], ["cms_media.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["media_id"], ["cms_media.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cover_media_id"], ["cms_media.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_cms_ai_video_jobs_site_id", "cms_ai_video_jobs", ["site_id"])
    op.create_index("ix_cms_ai_video_jobs_status", "cms_ai_video_jobs", ["status"])
    op.create_index("ix_cms_ai_video_jobs_created_at", "cms_ai_video_jobs", ["created_at"])
    op.create_index("ix_cms_ai_video_entry", "cms_ai_video_jobs", ["entry_id", "id"])
    op.create_index("ix_cms_ai_video_status", "cms_ai_video_jobs", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_cms_ai_video_status", table_name="cms_ai_video_jobs")
    op.drop_index("ix_cms_ai_video_entry", table_name="cms_ai_video_jobs")
    op.drop_index("ix_cms_ai_video_jobs_created_at", table_name="cms_ai_video_jobs")
    op.drop_index("ix_cms_ai_video_jobs_status", table_name="cms_ai_video_jobs")
    op.drop_index("ix_cms_ai_video_jobs_site_id", table_name="cms_ai_video_jobs")
    op.drop_table("cms_ai_video_jobs")
