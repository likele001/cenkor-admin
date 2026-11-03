"""补齐 6 张 CMS 表与 18 个字段的迁移（ORM 孤儿清理）

审计背景（2026-11-03）：
在「开源包全新安装」环境里跑 ORM ↔ 库结构比对，发现一批对象**任何迁移都没建过**
（公开链、闭源链都没有）—— 生产库是靠手工 SQL 补出来的，仓库里只留 ORM 定义。
后果：干净环境装完能启动，但一旦走到知识库 / 发布渠道 / 阅读统计 / 线索表单
这些功能就报「表或列不存在」。这与 2026-11-02 那次「12 张 AI 表缺建表迁移」
是同一类问题，上次没有扫干净。

本次补齐：
  表 6 张   cms_kb_docs / cms_kb_chunks / cms_publish_channels / cms_publish_jobs
            / cms_entry_stats_daily / cms_track_events
  列 18 个  app_submissions(5) / cms_ai_generations(4) / cms_entries(2)
            / cms_forms(2) / cms_pages(5)
  外键 2 个 fk_cms_entries_ai_generation / fk_cms_ai_generations_site

其中 app_submissions 的 5 列历史上由**闭源迁移** ext/20261020_0035_app_publish.py
添加。公开侧代码（seed 的内置应用上架）要用这几列，所以必须在公开链自备一份，
否则开源版 seed 会稳定报 UndefinedColumn。

表结构由生产库 `pg_dump --schema-only`（PostgreSQL 16.10）原样导出，
不凭 ORM 反推，避免类型、默认值、CHECK、部分索引出现偏差。

幂等：CREATE TABLE / SEQUENCE / INDEX 一律 IF NOT EXISTS；
ADD CONSTRAINT 包在 DO 块里捕获 duplicate_object / duplicate_table /
invalid_table_definition（重复主键抛的是 42P16 invalid_table_definition）。
ADD COLUMN 一律 IF NOT EXISTS，不触碰既有数据。

pgvector：cms_kb_chunks.vector 依赖 vector 扩展。与 core/20261031_1310 的既有
方案保持一致 —— 装了就用 vector(1024) + HNSW；没装则把该列降级为
``double precision[]``（列始终存在，ORM 不漂移，检索退化为应用内算余弦），
装好扩展后用 backend/scripts/enable_pgvector.py 升级列类型。

Revision ID: 20261103_1100_cms_orphan
Revises: 20261103_0930_sso_bindings
Create Date: 2026-11-03 11:00
"""

from __future__ import annotations

import logging

from alembic import op

revision: str = "20261103_1100_cms_orphan"
down_revision: str | None = "20261103_0930_sso_bindings"
branch_labels: str | None = None
depends_on: str | None = None

log = logging.getLogger("alembic.runtime.migration")

# 本迁移建的表（父表在前，downgrade 反序删除）
_TABLES = (
    "cms_kb_docs",
    "cms_kb_chunks",
    "cms_publish_channels",
    "cms_publish_jobs",
    "cms_entry_stats_daily",
    "cms_track_events",
)

# 不依赖 pgvector 的语句（其中 __KB_CHUNKS__ 是占位，运行时按扩展可用性替换）
_STATEMENTS = [
    "CREATE TABLE IF NOT EXISTS public.cms_entry_stats_daily ( id bigint NOT NULL, site_id integer DEFAULT 1 NOT NULL, entry_id integer NOT NULL, stat_date date NOT NULL, pv integer DEFAULT 0 NOT NULL, uv integer DEFAULT 0 NOT NULL, avg_duration_ms integer DEFAULT 0 NOT NULL, avg_scroll_pct smallint DEFAULT 0 NOT NULL, bounce_count integer DEFAULT 0 NOT NULL, conversion_count integer DEFAULT 0 NOT NULL, source character varying(16) DEFAULT 'self'::character varying NOT NULL, synced_at timestamp with time zone DEFAULT now() NOT NULL )",
    "COMMENT ON TABLE public.cms_entry_stats_daily IS '内容日汇总指标，可被第三方数据覆盖或并存'",
    "COMMENT ON COLUMN public.cms_entry_stats_daily.bounce_count IS '跳出：滚动<25% 且停留<10 秒'",
    "COMMENT ON COLUMN public.cms_entry_stats_daily.source IS 'self / baidu / ga / manual'",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_entry_stats_daily_id_seq START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_entry_stats_daily_id_seq OWNED BY public.cms_entry_stats_daily.id",
    "__KB_CHUNKS__",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_kb_chunks_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_kb_chunks_id_seq OWNED BY public.cms_kb_chunks.id",
    "CREATE TABLE IF NOT EXISTS public.cms_kb_docs ( id integer NOT NULL, site_id integer DEFAULT 1 NOT NULL, title character varying(200) NOT NULL, source_type character varying(20) DEFAULT 'upload'::character varying NOT NULL, file_name character varying(255) DEFAULT ''::character varying NOT NULL, mime character varying(120) DEFAULT ''::character varying NOT NULL, size_bytes integer DEFAULT 0 NOT NULL, category character varying(60) DEFAULT ''::character varying NOT NULL, note text DEFAULT ''::text NOT NULL, status character varying(20) DEFAULT 'pending'::character varying NOT NULL, error text DEFAULT ''::text NOT NULL, chars integer DEFAULT 0 NOT NULL, chunk_count integer DEFAULT 0 NOT NULL, indexed_chunks integer DEFAULT 0 NOT NULL, content_hash character varying(64) DEFAULT ''::character varying NOT NULL, embed_model character varying(80) DEFAULT ''::character varying NOT NULL, created_by integer, created_at timestamp with time zone DEFAULT now() NOT NULL, updated_at timestamp with time zone DEFAULT now() NOT NULL, deleted_at timestamp with time zone, content_text text DEFAULT ''::text NOT NULL )",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_kb_docs_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_kb_docs_id_seq OWNED BY public.cms_kb_docs.id",
    "CREATE TABLE IF NOT EXISTS public.cms_publish_channels ( id integer NOT NULL, site_id integer DEFAULT 1 NOT NULL, channel_key character varying(32) NOT NULL, name character varying(80) NOT NULL, channel_type character varying(20) NOT NULL, enabled boolean DEFAULT true NOT NULL, is_default boolean DEFAULT false NOT NULL, config jsonb DEFAULT '{}'::jsonb NOT NULL, created_at timestamp with time zone DEFAULT now() NOT NULL, updated_at timestamp with time zone DEFAULT now() NOT NULL )",
    "COMMENT ON TABLE public.cms_publish_channels IS '内容分发渠道配置'",
    "COMMENT ON COLUMN public.cms_publish_channels.channel_type IS 'builtin / webhook / wechat / export'",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_publish_channels_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_publish_channels_id_seq OWNED BY public.cms_publish_channels.id",
    "CREATE TABLE IF NOT EXISTS public.cms_publish_jobs ( id bigint NOT NULL, entry_id integer NOT NULL, channel_id integer NOT NULL, status character varying(16) DEFAULT 'pending'::character varying NOT NULL, attempts integer DEFAULT 0 NOT NULL, scheduled_at timestamp with time zone, started_at timestamp with time zone, finished_at timestamp with time zone, external_id character varying(200), external_url character varying(500), error text, payload jsonb, created_at timestamp with time zone DEFAULT now() NOT NULL, updated_at timestamp with time zone DEFAULT now() NOT NULL )",
    "COMMENT ON TABLE public.cms_publish_jobs IS '内容分发任务，按渠道独立执行与重试'",
    "COMMENT ON COLUMN public.cms_publish_jobs.status IS 'pending / running / success / failed / skipped'",
    "COMMENT ON COLUMN public.cms_publish_jobs.external_id IS '公众号 media_id、webhook 响应 id 等外部标识'",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_publish_jobs_id_seq START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_publish_jobs_id_seq OWNED BY public.cms_publish_jobs.id",
    "CREATE TABLE IF NOT EXISTS public.cms_track_events ( id bigint NOT NULL, site_id integer DEFAULT 1 NOT NULL, entry_id integer, event_type character varying(20) NOT NULL, visitor_id character varying(64) DEFAULT ''::character varying NOT NULL, session_id character varying(64) DEFAULT ''::character varying NOT NULL, path character varying(500) DEFAULT ''::character varying NOT NULL, referrer character varying(500) DEFAULT ''::character varying NOT NULL, utm_source character varying(80), utm_medium character varying(80), utm_campaign character varying(120), device character varying(16) DEFAULT ''::character varying NOT NULL, ip_hash character varying(32) DEFAULT ''::character varying NOT NULL, ua_hash character varying(32) DEFAULT ''::character varying NOT NULL, duration_ms integer DEFAULT 0 NOT NULL, scroll_pct smallint DEFAULT 0 NOT NULL, stat_date date NOT NULL, meta jsonb, created_at timestamp with time zone DEFAULT now() NOT NULL )",
    "COMMENT ON TABLE public.cms_track_events IS '内容埋点原始事件（PV / 心跳 / 滚动 / 转化）'",
    "COMMENT ON COLUMN public.cms_track_events.ip_hash IS 'IP 的不可逆摘要，不存明文 IP'",
    "COMMENT ON COLUMN public.cms_track_events.ua_hash IS 'User-Agent 摘要，不存原始 UA'",
    "COMMENT ON COLUMN public.cms_track_events.stat_date IS '业务时区 Asia/Shanghai 的自然日，聚合前算好'",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_track_events_id_seq START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_track_events_id_seq OWNED BY public.cms_track_events.id",
    "ALTER TABLE ONLY public.cms_entry_stats_daily ALTER COLUMN id SET DEFAULT nextval('public.cms_entry_stats_daily_id_seq'::regclass)",
    "ALTER TABLE ONLY public.cms_kb_chunks ALTER COLUMN id SET DEFAULT nextval('public.cms_kb_chunks_id_seq'::regclass)",
    "ALTER TABLE ONLY public.cms_kb_docs ALTER COLUMN id SET DEFAULT nextval('public.cms_kb_docs_id_seq'::regclass)",
    "ALTER TABLE ONLY public.cms_publish_channels ALTER COLUMN id SET DEFAULT nextval('public.cms_publish_channels_id_seq'::regclass)",
    "ALTER TABLE ONLY public.cms_publish_jobs ALTER COLUMN id SET DEFAULT nextval('public.cms_publish_jobs_id_seq'::regclass)",
    "ALTER TABLE ONLY public.cms_track_events ALTER COLUMN id SET DEFAULT nextval('public.cms_track_events_id_seq'::regclass)",
    "DO $do$ BEGIN ALTER TABLE public.cms_entry_stats_daily ADD CONSTRAINT cms_entry_stats_daily_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE public.cms_kb_chunks ADD CONSTRAINT cms_kb_chunks_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE public.cms_kb_docs ADD CONSTRAINT cms_kb_docs_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE public.cms_publish_channels ADD CONSTRAINT cms_publish_channels_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE public.cms_publish_jobs ADD CONSTRAINT cms_publish_jobs_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE public.cms_track_events ADD CONSTRAINT cms_track_events_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE public.cms_entry_stats_daily ADD CONSTRAINT uq_entry_stats_daily UNIQUE (entry_id, stat_date, source); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE public.cms_publish_channels ADD CONSTRAINT uq_publish_channel_key UNIQUE (channel_key); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "CREATE INDEX IF NOT EXISTS ix_cms_kb_chunks_doc ON public.cms_kb_chunks USING btree (doc_id)",
    "CREATE INDEX IF NOT EXISTS ix_cms_kb_docs_hash ON public.cms_kb_docs USING btree (site_id, content_hash) WHERE ((deleted_at IS NULL) AND ((content_hash)::text <> ''::text))",
    "CREATE INDEX IF NOT EXISTS ix_cms_kb_docs_site ON public.cms_kb_docs USING btree (site_id, created_at DESC) WHERE (deleted_at IS NULL)",
    "CREATE INDEX IF NOT EXISTS ix_cms_kb_docs_status ON public.cms_kb_docs USING btree (status) WHERE (deleted_at IS NULL)",
    "CREATE INDEX IF NOT EXISTS ix_entry_stats_date ON public.cms_entry_stats_daily USING btree (stat_date)",
    "CREATE INDEX IF NOT EXISTS ix_entry_stats_entry ON public.cms_entry_stats_daily USING btree (entry_id, stat_date DESC)",
    "CREATE INDEX IF NOT EXISTS ix_entry_stats_site_date ON public.cms_entry_stats_daily USING btree (site_id, stat_date)",
    "CREATE INDEX IF NOT EXISTS ix_publish_jobs_channel ON public.cms_publish_jobs USING btree (channel_id)",
    "CREATE INDEX IF NOT EXISTS ix_publish_jobs_entry ON public.cms_publish_jobs USING btree (entry_id)",
    "CREATE INDEX IF NOT EXISTS ix_publish_jobs_status ON public.cms_publish_jobs USING btree (status, scheduled_at)",
    "CREATE INDEX IF NOT EXISTS ix_track_events_entry_date ON public.cms_track_events USING btree (entry_id, stat_date)",
    "CREATE INDEX IF NOT EXISTS ix_track_events_ip_date ON public.cms_track_events USING btree (ip_hash, stat_date)",
    "CREATE INDEX IF NOT EXISTS ix_track_events_site_date ON public.cms_track_events USING btree (site_id, stat_date)",
    "CREATE INDEX IF NOT EXISTS ix_track_events_stat_date ON public.cms_track_events USING btree (stat_date)",
    "CREATE INDEX IF NOT EXISTS ix_track_events_type_date ON public.cms_track_events USING btree (event_type, stat_date)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_kb_chunk_seq ON public.cms_kb_chunks USING btree (doc_id, seq)",
    "DO $do$ BEGIN ALTER TABLE public.cms_kb_chunks ADD CONSTRAINT cms_kb_chunks_doc_id_fkey FOREIGN KEY (doc_id) REFERENCES public.cms_kb_docs(id) ON DELETE CASCADE; EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
]

# cms_kb_chunks 建表的两个版本：带向量列 / 不带向量列
_KB_CHUNKS_WITH_VECTOR = "CREATE TABLE IF NOT EXISTS public.cms_kb_chunks ( id integer NOT NULL, doc_id integer NOT NULL, seq integer NOT NULL, heading character varying(200) DEFAULT ''::character varying NOT NULL, heading_path character varying(400) DEFAULT ''::character varying NOT NULL, text text NOT NULL, chars integer DEFAULT 0 NOT NULL, vector public.vector(1024), dim integer DEFAULT 0 NOT NULL, content_hash character varying(64) DEFAULT ''::character varying NOT NULL, model character varying(80) DEFAULT ''::character varying NOT NULL, created_at timestamp with time zone DEFAULT now() NOT NULL )"
_KB_CHUNKS_NO_VECTOR = "CREATE TABLE IF NOT EXISTS public.cms_kb_chunks ( id integer NOT NULL, doc_id integer NOT NULL, seq integer NOT NULL, heading character varying(200) DEFAULT ''::character varying NOT NULL, heading_path character varying(400) DEFAULT ''::character varying NOT NULL, text text NOT NULL, chars integer DEFAULT 0 NOT NULL, vector double precision[], dim integer DEFAULT 0 NOT NULL, content_hash character varying(64) DEFAULT ''::character varying NOT NULL, model character varying(80) DEFAULT ''::character varying NOT NULL, created_at timestamp with time zone DEFAULT now() NOT NULL )"

# 依赖 pgvector 的语句（无扩展时整组跳过）
_VECTOR_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS ix_cms_kb_chunks_vec ON public.cms_kb_chunks USING hnsw (vector public.vector_cosine_ops)",
]

# 补列（IF NOT EXISTS，已有列的环境自动跳过）
_COLUMN_STATEMENTS = [
    "ALTER TABLE public.app_submissions ADD COLUMN IF NOT EXISTS changelog text",
    "ALTER TABLE public.app_submissions ADD COLUMN IF NOT EXISTS min_core_version character varying(20)",
    "ALTER TABLE public.app_submissions ADD COLUMN IF NOT EXISTS published_at timestamp with time zone",
    "ALTER TABLE public.app_submissions ADD COLUMN IF NOT EXISTS schema_version integer",
    "ALTER TABLE public.app_submissions ADD COLUMN IF NOT EXISTS yanked_at timestamp with time zone",
    "ALTER TABLE public.cms_ai_generations ADD COLUMN IF NOT EXISTS cost numeric(16,6)",
    "ALTER TABLE public.cms_ai_generations ADD COLUMN IF NOT EXISTS currency character varying(8) DEFAULT 'CNY'::character varying NOT NULL",
    "ALTER TABLE public.cms_ai_generations ADD COLUMN IF NOT EXISTS site_id integer DEFAULT 1 NOT NULL",
    "ALTER TABLE public.cms_ai_generations ADD COLUMN IF NOT EXISTS tokens_cache integer DEFAULT 0 NOT NULL",
    "ALTER TABLE public.cms_entries ADD COLUMN IF NOT EXISTS ai_generation_id integer",
    "ALTER TABLE public.cms_entries ADD COLUMN IF NOT EXISTS ai_origin character varying(32)",
    "ALTER TABLE public.cms_forms ADD COLUMN IF NOT EXISTS create_lead boolean DEFAULT false NOT NULL",
    "ALTER TABLE public.cms_forms ADD COLUMN IF NOT EXISTS lead_mapping jsonb DEFAULT '{}'::jsonb NOT NULL",
    "ALTER TABLE public.cms_pages ADD COLUMN IF NOT EXISTS ai_generation_id integer",
    "ALTER TABLE public.cms_pages ADD COLUMN IF NOT EXISTS kind character varying(20) DEFAULT 'page'::character varying NOT NULL",
    "ALTER TABLE public.cms_pages ADD COLUMN IF NOT EXISTS nav jsonb DEFAULT '[]'::jsonb NOT NULL",
    "ALTER TABLE public.cms_pages ADD COLUMN IF NOT EXISTS seo jsonb DEFAULT '{}'::jsonb NOT NULL",
    "ALTER TABLE public.cms_pages ADD COLUMN IF NOT EXISTS site_key character varying(60)",
    "DO $do$ BEGIN ALTER TABLE public.cms_entries ADD CONSTRAINT fk_cms_entries_ai_generation FOREIGN KEY (ai_generation_id) REFERENCES public.cms_ai_generations(id) ON DELETE SET NULL; EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE public.cms_ai_generations ADD CONSTRAINT fk_cms_ai_generations_site FOREIGN KEY (site_id) REFERENCES public.cms_sites(id) ON DELETE RESTRICT; EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
]


def _run(bind, stmt: str) -> None:
    """执行一条原生 DDL。

    exec_driver_sql 走 DBAPI 的参数风格，语句里的 ``%``（例如表注释
    「滚动<25% 且停留<10 秒」）会被当成参数占位符，抛
    ``immutabledict is not a sequence``。所以统一转义成 ``%%``。
    """
    bind.exec_driver_sql(stmt.replace("%", "%%"))


def _has_vector(bind) -> bool:
    """已安装 vector 扩展？——查系统表即可，不需要超管权限。"""
    try:
        row = bind.exec_driver_sql(
            "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
        ).first()
    except Exception:
        return False
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()

    # pgvector：先看是否已装（业务账号通常没有 CREATE EXTENSION 权限，
    # 但扩展一般已由 DBA 预装好）。没装才尝试，失败则降级。
    vector_ok = _has_vector(bind)
    if not vector_ok:
        try:
            with bind.begin_nested():
                bind.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            vector_ok = True
        except Exception as exc:  # 缺扩展属预期降级路径
            log.warning(
                "cms.kb.pgvector_unavailable error=%s —— 跳过向量列与 HNSW 索引，"
                "知识库向量检索不可用；安装 pgvector 后重跑本迁移即可补齐", exc,
            )

    for stmt in _STATEMENTS:
        if stmt == "__KB_CHUNKS__":
            stmt = _KB_CHUNKS_WITH_VECTOR if vector_ok else _KB_CHUNKS_NO_VECTOR
        _run(bind, stmt)

    if vector_ok:
        for stmt in _VECTOR_STATEMENTS:
            # HNSW 需要 pgvector >= 0.5。低版本或权限不足时只跳过索引，
            # 不影响建表与其余功能。
            try:
                with bind.begin_nested():
                    _run(bind, stmt)
            except Exception as exc:  # 索引不可用属降级，不阻塞安装
                log.warning(
                    "cms.kb.vector_index_skipped error=%s stmt=%s", exc, stmt[:100]
                )

    for stmt in _COLUMN_STATEMENTS:
        _run(bind, stmt)


def downgrade() -> None:
    """回滚只删本迁移建的表。补过的列**不回滚** —— 那些列上可能已有业务数据，
    删列不可逆，需要人工确认，不适合放在自动回滚里。"""
    bind = op.get_bind()
    for table in reversed(_TABLES):
        bind.exec_driver_sql(f"DROP TABLE IF EXISTS public.{table} CASCADE")
