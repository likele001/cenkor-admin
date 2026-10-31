"""CMS AI 层：embeddings / generations / providers / capabilities / prompts

本迁移接管原先散在三处的建表逻辑（2026-10-31 统一到 alembic）：

1. `apps/cms/ai/schema.sql`（应用启动 bootstrap 执行的四张表）
2. `backend/migrations/003_embed_dims.sql`（embedding 能力降到 1024 维）
3. `backend/migrations/004_vector_pgvector.sql`（double[] → pgvector + HNSW）
4. `backend/migrations/006_ai_prompts.sql`（提示词版本表）

为什么必须收进 alembic：bootstrap 在**应用启动时**跑，而 alembic 在**启动前**跑。
003/004 要 ALTER 的表由 bootstrap 建，等于「后来者 ALTER 还没建的表」——
新装时必然失败，所以这两条 SQL 从来没在任何环境自动执行过，只在生产手工跑过一次。

pgvector 处理（关键）：
- 扩展可用 → `vector(1024)` + HNSW 余弦索引（生产现状）
- 扩展不可用（CI / docker 的 postgres:16-alpine）→ 退回 `double precision[]`，
  与应用 bootstrap 过去建出来的形态一致，语义检索降级为应用内算余弦，**不报错**。
  装好 pgvector 后用 `backend/scripts/enable_pgvector.py` 把列升级上去。

Revision ID: 20261031_1310_cms_ai_tables   （27 字符，alembic_version 上限 32）
Revises: 20261031_1300_cms_multisite
Create Date: 2026-10-31 13:10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from loguru import logger
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261031_1310_cms_ai_tables"
down_revision: str | Sequence[str] | None = "20261031_1300_cms_multisite"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBED_DIM = 1024


def _try(sql: str, hint: str = "") -> bool:
    """在保存点里执行一条可能失败的 DDL：失败只回滚本语句，不带崩整个迁移。"""
    conn = op.get_bind()
    try:
        with conn.begin_nested():
            conn.exec_driver_sql(sql)
        return True
    except Exception as exc:
        # 用 f-string 而不是 kwargs：运维看日志时得一眼看到原因，不该再去翻结构化字段
        logger.warning(
            f"migration.ai.degraded: {sql[:70]} -> {str(exc).splitlines()[0][:160]}" + hint
        )
        return False


def _has_pgvector() -> bool:
    conn = op.get_bind()
    row = conn.exec_driver_sql(
        "select 1 from pg_extension where extname = 'vector'"
    ).first()
    return row is not None


def upgrade() -> None:
    # ---- 1) pgvector：能装就装，装不上降级 ----------------------------------
    if not _has_pgvector():
        _try(
            "CREATE EXTENSION IF NOT EXISTS vector",
            hint="｜向量列将降级为 double precision[]。"
                 "请用超级用户在该库执行一次 CREATE EXTENSION vector，"
                 "再跑 backend/scripts/enable_pgvector.py 升级列类型。",
        )
    has_vector = _has_pgvector()

    # ---- 2) 服务商通道（capabilities 依赖它，必须在前）-----------------------
    op.create_table(
        "cms_ai_providers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="openai"),
        sa.Column("base_url", sa.String(400), nullable=False),
        sa.Column("api_key_enc", sa.Text(), nullable=False, server_default=""),
        sa.Column("api_key_hint", sa.String(16), nullable=False, server_default=""),
        sa.Column("extra_headers", postgresql.JSONB(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("remark", sa.String(255), nullable=True),
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("last_test_error", sa.Text(), nullable=True),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_cms_ai_providers_enabled", "cms_ai_providers", ["enabled"])

    # ---- 3) 能力绑定 ---------------------------------------------------------
    op.create_table(
        "cms_ai_capabilities",
        sa.Column("capability", sa.String(32), primary_key=True),
        sa.Column(
            "provider_id",
            sa.Integer(),
            sa.ForeignKey("cms_ai_providers.id", ondelete="RESTRICT", name="fk_cms_ai_cap_provider"),
            nullable=True,
        ),
        sa.Column("model", sa.String(160), nullable=False, server_default=""),
        sa.Column("params", postgresql.JSONB(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_cms_ai_capabilities_provider_id", "cms_ai_capabilities", ["provider_id"])

    # ---- 4) 生成流水 ---------------------------------------------------------
    op.create_table(
        "cms_ai_generations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("target", sa.String(80), nullable=False, server_default=""),
        sa.Column("provider", sa.String(40), nullable=False, server_default=""),
        sa.Column("model", sa.String(80), nullable=False, server_default=""),
        sa.Column("prompt_digest", sa.String(64), nullable=False, server_default=""),
        sa.Column("params", postgresql.JSONB(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ok"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for name, cols in (
        ("ix_cms_ai_generations_kind", ["kind"]),
        ("ix_cms_ai_generations_status", ["status"]),
        ("ix_cms_ai_generations_created_at", ["created_at"]),
        ("ix_cms_ai_gen_target", ["kind", "target"]),
    ):
        op.create_index(name, "cms_ai_generations", cols)

    # ---- 5) 提示词版本表（原 006）-------------------------------------------
    op.create_table(
        "cms_ai_prompts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("prompt_key", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_ai_prompts_key", "cms_ai_prompts", ["prompt_key"])

    # 老库已存在该表时上面的 create_table 会被幂等层跳过，
    # 约束/索引得单独收敛一遍，否则老库永远缺这几个护栏。
    op.execute(
        "DO $$ BEGIN "
        "IF to_regclass('public.cms_ai_prompts') IS NULL THEN RETURN; END IF; "
        "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_ai_prompt_key_ver' "
        "AND conrelid = 'public.cms_ai_prompts'::regclass) THEN "
        "ALTER TABLE cms_ai_prompts ADD CONSTRAINT uq_ai_prompt_key_ver "
        "UNIQUE (prompt_key, version); END IF; "
        "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_ai_prompt_nonempty' "
        "AND conrelid = 'public.cms_ai_prompts'::regclass) THEN "
        "ALTER TABLE cms_ai_prompts ADD CONSTRAINT ck_ai_prompt_nonempty "
        "CHECK (length(btrim(content)) > 0); END IF; "
        "END $$;"
    )
    # 每个 key 同时只能有一个激活版本：靠 DB 保证，不靠应用层自觉
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_prompt_active "
        "ON cms_ai_prompts (prompt_key) WHERE is_active"
    )

    # ---- 6) 向量表 -----------------------------------------------------------
    # 四张表里只有这张带向量列，所以用裸 SQL：列类型取决于扩展在不在。
    vec_type = f"vector({EMBED_DIM})" if has_vector else "double precision[]"
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS cms_embeddings (
          id           SERIAL PRIMARY KEY,
          entry_id     INTEGER NOT NULL REFERENCES cms_entries(id) ON DELETE CASCADE,
          field        VARCHAR(40) NOT NULL DEFAULT 'combined',
          lang         VARCHAR(16) NOT NULL DEFAULT 'base',
          vector       {vec_type},
          dim          INTEGER NOT NULL DEFAULT 0,
          content_hash VARCHAR(64) NOT NULL DEFAULT '',
          model        VARCHAR(80) NOT NULL DEFAULT '',
          created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT uq_cms_embedding_target UNIQUE (entry_id, field, lang)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cms_embeddings_entry_id ON cms_embeddings (entry_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_cms_embeddings_model ON cms_embeddings (model)")

    # 老库如果还是 double precision[]（004 没跑过），这里顺手升级成向量列。
    # 旧向量是 2048 维（豆包默认），装不进 1024 维列 —— 只能清空由应用重建，
    # 这正是 004 当初的行为，逻辑原样保留。
    if has_vector:
        col_type = op.get_bind().exec_driver_sql(
            "select udt_name from information_schema.columns "
            "where table_name = 'cms_embeddings' and column_name = 'vector'"
        ).scalar()
        if col_type != "vector":
            logger.info("migration.ai.embed_upgrade", from_type=col_type)
            op.execute("DROP INDEX IF EXISTS ix_cms_embeddings_hnsw")
            op.execute("DELETE FROM cms_embeddings")
            op.execute("ALTER TABLE cms_embeddings DROP COLUMN IF EXISTS vector")
            op.execute(f"ALTER TABLE cms_embeddings ADD COLUMN vector vector({EMBED_DIM})")
        op.execute(
            "COMMENT ON COLUMN cms_embeddings.vector IS "
            "'pgvector 向量，1024 维（豆包 dimensions=1024）；HNSW 余弦索引'"
        )
        # HNSW 需要 pgvector >= 0.5；老版本扩展上建不出来就降级（有列没索引，照样能查）
        _try(
            "CREATE INDEX IF NOT EXISTS ix_cms_embeddings_hnsw "
            "ON cms_embeddings USING hnsw (vector vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )

    # ---- 7) embedding 能力统一降到 1024 维（原 003）-------------------------
    # 注意 params 里可能是 jsonb 的 'null' 值（不是 SQL NULL），
    # COALESCE 不生效，直接 || 会拼成 [null, {...}]，所以按 jsonb_typeof 判。
    op.execute(
        """
        UPDATE cms_ai_capabilities
        SET params = CASE
              WHEN params IS NULL
                OR jsonb_typeof(params) IS NULL
                OR jsonb_typeof(params) <> 'object'
              THEN jsonb_build_object('dimensions', %(dim)s)
              ELSE params || jsonb_build_object('dimensions', %(dim)s)
            END
        WHERE capability = 'embedding'
          AND COALESCE(params -> 'dimensions', 'null'::jsonb) <> to_jsonb(%(dim)s::int)
        """ % {"dim": EMBED_DIM}
    )


def downgrade() -> None:
    # 警告：老库里这四张表不是本迁移建的（原本由 bootstrap 建），
    # downgrade 会连数据一起删。项目规范 §11 明确回退走备份恢复，不走 downgrade。
    # 只拆本迁移建的对象。向量列的数据无法还原（升级时已按 004 的语义清空）。
    op.execute("DROP INDEX IF EXISTS ix_cms_embeddings_hnsw")
    op.execute("DROP TABLE IF EXISTS cms_embeddings")
    op.execute("DROP INDEX IF EXISTS uq_ai_prompt_active")
    op.execute("DROP INDEX IF EXISTS idx_ai_prompts_key")
    op.execute("DROP TABLE IF EXISTS cms_ai_prompts")
    for name in (
        "ix_cms_ai_gen_target",
        "ix_cms_ai_generations_created_at",
        "ix_cms_ai_generations_status",
        "ix_cms_ai_generations_kind",
    ):
        op.execute(f"DROP INDEX IF EXISTS {name}")
    op.execute("DROP TABLE IF EXISTS cms_ai_generations")
    op.execute("DROP INDEX IF EXISTS ix_cms_ai_capabilities_provider_id")
    op.execute("DROP TABLE IF EXISTS cms_ai_capabilities")
    op.execute("DROP INDEX IF EXISTS ix_cms_ai_providers_enabled")
    op.execute("DROP TABLE IF EXISTS cms_ai_providers")
