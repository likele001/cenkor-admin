"""CMS AI 层：补齐 12 张表的建表迁移

审计背景（2026-11-02）：
公开仓库的 AI 模块代码是完整的（37 个文件全在版本控制里），但这 12 张表的建表
语句历史上从未提交 —— 生产库是靠手工 SQL 建起来的，仓库里只留下 ORM 定义。
后果：干净环境跑完 `alembic upgrade heads` 后，AI 批量生产 / 记忆 / 定价 / 质检 /
会话 / AB 测试 / 内容摘要 / 工作流编排这些页面一打开就报「表不存在」。

表结构全部由生产库 `pg_dump --schema-only` 原样导出（PostgreSQL 16.10），
不凭 ORM 反推，避免类型、默认值、CHECK 约束、部分唯一索引出现偏差。

幂等处理（生产库表已存在，升级时必须安全跳过）：
- CREATE TABLE / SEQUENCE / INDEX 一律 IF NOT EXISTS
- ADD CONSTRAINT 包在 DO 块里，捕获 duplicate_object / duplicate_table

Revision ID: 20261102_2140_cms_ai_missing
Revises: 20261102_1215_cms_entry_links
Create Date: 2026-11-02 21:40
"""

from __future__ import annotations

from alembic import op

revision: str = "20261102_2140_cms_ai_missing"
down_revision: str | None = "20261102_1215_cms_entry_links"
branch_labels: str | None = None
depends_on: str | None = None


# 表 -> 依赖顺序（父表在前，供 downgrade 反序删除）
_TABLES = (
    "cms_ai_batch_jobs",
    "cms_ai_batch_items",
    "cms_ai_sessions",
    "cms_ai_session_turns",
    "cms_ai_reviews",
    "cms_ai_prices",
    "cms_ai_memory",
    "cms_ai_entry_digests",
    "cms_ai_ab_runs",
    "cms_workflows",
    "cms_workflow_runs",
    "cms_workflow_steps",
)

_STATEMENTS = [
    "CREATE TABLE IF NOT EXISTS public.cms_ai_ab_runs ( id integer NOT NULL, site_id integer DEFAULT 1 NOT NULL, topic text NOT NULL, provider character varying(60) DEFAULT ''::character varying NOT NULL, left_model character varying(120) DEFAULT ''::character varying NOT NULL, right_model character varying(120) DEFAULT ''::character varying NOT NULL, left_text text DEFAULT ''::text NOT NULL, right_text text DEFAULT ''::text NOT NULL, left_ms integer DEFAULT 0 NOT NULL, right_ms integer DEFAULT 0 NOT NULL, left_error text, right_error text, winner character varying(10), note text DEFAULT ''::text NOT NULL, created_by integer, created_at timestamp with time zone DEFAULT now() NOT NULL, reviewed_at timestamp with time zone, CONSTRAINT ck_ai_ab_winner CHECK (((winner IS NULL) OR ((winner)::text = ANY ((ARRAY['left'::character varying, 'right'::character varying, 'tie'::character varying])::text[])))) )",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_ai_ab_runs_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_ai_ab_runs_id_seq OWNED BY public.cms_ai_ab_runs.id",
    "CREATE TABLE IF NOT EXISTS public.cms_ai_batch_items ( id integer NOT NULL, job_id integer NOT NULL, site_id integer NOT NULL, seq integer NOT NULL, brief text NOT NULL, status character varying(20) DEFAULT 'pending'::character varying NOT NULL, entry_id integer, title character varying(200), error text, attempts smallint DEFAULT 0 NOT NULL, tokens_in integer DEFAULT 0 NOT NULL, tokens_out integer DEFAULT 0 NOT NULL, started_at timestamp with time zone, finished_at timestamp with time zone, CONSTRAINT ck_batch_item_status CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'running'::character varying, 'done'::character varying, 'failed'::character varying, 'skipped'::character varying])::text[]))) )",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_ai_batch_items_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_ai_batch_items_id_seq OWNED BY public.cms_ai_batch_items.id",
    "CREATE TABLE IF NOT EXISTS public.cms_ai_batch_jobs ( id integer NOT NULL, site_id integer NOT NULL, name character varying(120) NOT NULL, content_type_id integer NOT NULL, content_type_key character varying(60) NOT NULL, status character varying(20) DEFAULT 'pending'::character varying NOT NULL, lang character varying(20) DEFAULT 'zh-CN'::character varying NOT NULL, total integer DEFAULT 0 NOT NULL, succeeded integer DEFAULT 0 NOT NULL, failed integer DEFAULT 0 NOT NULL, skipped integer DEFAULT 0 NOT NULL, concurrency smallint DEFAULT 1 NOT NULL, last_error text, created_by integer, created_at timestamp with time zone DEFAULT now() NOT NULL, started_at timestamp with time zone, finished_at timestamp with time zone, CONSTRAINT ck_batch_job_concurrency CHECK (((concurrency >= 1) AND (concurrency <= 4))), CONSTRAINT ck_batch_job_counts CHECK (((total >= 0) AND (succeeded >= 0) AND (failed >= 0) AND (skipped >= 0))), CONSTRAINT ck_batch_job_status CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'running'::character varying, 'paused'::character varying, 'done'::character varying, 'cancelled'::character varying])::text[]))) )",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_ai_batch_jobs_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_ai_batch_jobs_id_seq OWNED BY public.cms_ai_batch_jobs.id",
    "CREATE TABLE IF NOT EXISTS public.cms_ai_entry_digests ( id integer NOT NULL, site_id integer DEFAULT 1 NOT NULL, entry_id integer NOT NULL, title character varying(300) DEFAULT ''::character varying NOT NULL, digest text DEFAULT ''::text NOT NULL, topics text[] DEFAULT '{}'::text[] NOT NULL, entities jsonb, content_hash character varying(64) DEFAULT ''::character varying NOT NULL, built_at timestamp with time zone DEFAULT now() NOT NULL )",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_ai_entry_digests_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_ai_entry_digests_id_seq OWNED BY public.cms_ai_entry_digests.id",
    "CREATE TABLE IF NOT EXISTS public.cms_ai_memory ( id integer NOT NULL, site_id integer DEFAULT 1 NOT NULL, scope character varying(24) NOT NULL, key character varying(120) DEFAULT ''::character varying NOT NULL, content text NOT NULL, weight integer DEFAULT 50 NOT NULL, enabled boolean DEFAULT true NOT NULL, source character varying(16) DEFAULT 'manual'::character varying NOT NULL, status character varying(16) DEFAULT 'approved'::character varying NOT NULL, injection_count integer DEFAULT 0 NOT NULL, created_by integer, created_at timestamp with time zone DEFAULT now() NOT NULL, updated_at timestamp with time zone DEFAULT now() NOT NULL )",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_ai_memory_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_ai_memory_id_seq OWNED BY public.cms_ai_memory.id",
    "CREATE TABLE IF NOT EXISTS public.cms_ai_prices ( id bigint NOT NULL, provider character varying(64) DEFAULT ''::character varying NOT NULL, model character varying(160) DEFAULT ''::character varying NOT NULL, kind character varying(32) DEFAULT ''::character varying NOT NULL, input_per_m numeric(14,4) DEFAULT 0 NOT NULL, output_per_m numeric(14,4) DEFAULT 0 NOT NULL, currency character varying(8) DEFAULT 'CNY'::character varying NOT NULL, enabled boolean DEFAULT true NOT NULL, note character varying(200) DEFAULT ''::character varying NOT NULL, created_at timestamp with time zone DEFAULT now() NOT NULL, updated_at timestamp with time zone DEFAULT now() NOT NULL, unit character varying(8) DEFAULT 'token'::character varying NOT NULL, cache_per_m numeric(14,4) )",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_ai_prices_id_seq START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_ai_prices_id_seq OWNED BY public.cms_ai_prices.id",
    "CREATE TABLE IF NOT EXISTS public.cms_ai_reviews ( id integer NOT NULL, site_id integer DEFAULT 1 NOT NULL, entry_id integer, generation_id integer, source character varying(20) DEFAULT 'sample'::character varying NOT NULL, ab_run_id integer, kind character varying(40) DEFAULT 'entry_draft'::character varying NOT NULL, provider character varying(60) DEFAULT ''::character varying NOT NULL, model character varying(120) DEFAULT ''::character varying NOT NULL, overall double precision DEFAULT 0 NOT NULL, scores jsonb, verdict character varying(20) DEFAULT 'pass'::character varying NOT NULL, note text DEFAULT ''::text NOT NULL, reviewer_id integer, created_at timestamp with time zone DEFAULT now() NOT NULL, CONSTRAINT ck_ai_review_overall CHECK (((overall >= (0)::double precision) AND (overall <= (5)::double precision))), CONSTRAINT ck_ai_review_source CHECK (((source)::text = ANY ((ARRAY['sample'::character varying, 'ab'::character varying])::text[]))), CONSTRAINT ck_ai_review_verdict CHECK (((verdict)::text = ANY ((ARRAY['pass'::character varying, 'needs_fix'::character varying, 'reject'::character varying])::text[]))) )",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_ai_reviews_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_ai_reviews_id_seq OWNED BY public.cms_ai_reviews.id",
    "CREATE TABLE IF NOT EXISTS public.cms_ai_session_turns ( id integer NOT NULL, session_id integer NOT NULL, role character varying(16) DEFAULT 'system'::character varying NOT NULL, kind character varying(32) NOT NULL, content text NOT NULL, meta jsonb, created_by integer, created_at timestamp with time zone DEFAULT now() NOT NULL )",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_ai_session_turns_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_ai_session_turns_id_seq OWNED BY public.cms_ai_session_turns.id",
    "CREATE TABLE IF NOT EXISTS public.cms_ai_sessions ( id integer NOT NULL, site_id integer, session_key character varying(80) NOT NULL, entry_id integer, title character varying(200), turn_count integer DEFAULT 0 NOT NULL, created_by integer, created_at timestamp with time zone DEFAULT now() NOT NULL, updated_at timestamp with time zone DEFAULT now() NOT NULL )",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_ai_sessions_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_ai_sessions_id_seq OWNED BY public.cms_ai_sessions.id",
    "CREATE TABLE IF NOT EXISTS public.cms_workflow_runs ( id integer NOT NULL, workflow_id integer NOT NULL, site_id integer NOT NULL, status character varying(20) DEFAULT 'pending'::character varying NOT NULL, trigger character varying(20) DEFAULT 'manual'::character varying NOT NULL, input jsonb DEFAULT '{}'::jsonb NOT NULL, vars jsonb DEFAULT '{}'::jsonb NOT NULL, error text, created_by integer, created_at timestamp with time zone DEFAULT now() NOT NULL, started_at timestamp with time zone, finished_at timestamp with time zone )",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_workflow_runs_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_workflow_runs_id_seq OWNED BY public.cms_workflow_runs.id",
    "CREATE TABLE IF NOT EXISTS public.cms_workflow_steps ( id integer NOT NULL, run_id integer NOT NULL, node_id character varying(60) NOT NULL, node_type character varying(60) NOT NULL, seq integer DEFAULT 0 NOT NULL, title character varying(200), status character varying(20) DEFAULT 'pending'::character varying NOT NULL, input jsonb DEFAULT '{}'::jsonb NOT NULL, output jsonb DEFAULT '{}'::jsonb NOT NULL, error text, attempts integer DEFAULT 0 NOT NULL, duration_ms integer DEFAULT 0 NOT NULL, started_at timestamp with time zone, finished_at timestamp with time zone )",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_workflow_steps_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_workflow_steps_id_seq OWNED BY public.cms_workflow_steps.id",
    "CREATE TABLE IF NOT EXISTS public.cms_workflows ( id integer NOT NULL, site_id integer NOT NULL, name character varying(120) NOT NULL, description text, status character varying(20) DEFAULT 'draft'::character varying NOT NULL, graph jsonb DEFAULT '{\"edges\": [], \"nodes\": []}'::jsonb NOT NULL, trigger_type character varying(20) DEFAULT 'manual'::character varying NOT NULL, cron character varying(80), next_run_at timestamp with time zone, last_run_id integer, last_run_status character varying(20), run_count integer DEFAULT 0 NOT NULL, created_by integer, created_at timestamp with time zone DEFAULT now() NOT NULL, updated_at timestamp with time zone DEFAULT now() NOT NULL )",
    "CREATE SEQUENCE IF NOT EXISTS public.cms_workflows_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.cms_workflows_id_seq OWNED BY public.cms_workflows.id",
    "ALTER TABLE ONLY public.cms_ai_ab_runs ALTER COLUMN id SET DEFAULT nextval('public.cms_ai_ab_runs_id_seq'::regclass)",
    "ALTER TABLE ONLY public.cms_ai_batch_items ALTER COLUMN id SET DEFAULT nextval('public.cms_ai_batch_items_id_seq'::regclass)",
    "ALTER TABLE ONLY public.cms_ai_batch_jobs ALTER COLUMN id SET DEFAULT nextval('public.cms_ai_batch_jobs_id_seq'::regclass)",
    "ALTER TABLE ONLY public.cms_ai_entry_digests ALTER COLUMN id SET DEFAULT nextval('public.cms_ai_entry_digests_id_seq'::regclass)",
    "ALTER TABLE ONLY public.cms_ai_memory ALTER COLUMN id SET DEFAULT nextval('public.cms_ai_memory_id_seq'::regclass)",
    "ALTER TABLE ONLY public.cms_ai_prices ALTER COLUMN id SET DEFAULT nextval('public.cms_ai_prices_id_seq'::regclass)",
    "ALTER TABLE ONLY public.cms_ai_reviews ALTER COLUMN id SET DEFAULT nextval('public.cms_ai_reviews_id_seq'::regclass)",
    "ALTER TABLE ONLY public.cms_ai_session_turns ALTER COLUMN id SET DEFAULT nextval('public.cms_ai_session_turns_id_seq'::regclass)",
    "ALTER TABLE ONLY public.cms_ai_sessions ALTER COLUMN id SET DEFAULT nextval('public.cms_ai_sessions_id_seq'::regclass)",
    "ALTER TABLE ONLY public.cms_workflow_runs ALTER COLUMN id SET DEFAULT nextval('public.cms_workflow_runs_id_seq'::regclass)",
    "ALTER TABLE ONLY public.cms_workflow_steps ALTER COLUMN id SET DEFAULT nextval('public.cms_workflow_steps_id_seq'::regclass)",
    "ALTER TABLE ONLY public.cms_workflows ALTER COLUMN id SET DEFAULT nextval('public.cms_workflows_id_seq'::regclass)",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_ab_runs ADD CONSTRAINT cms_ai_ab_runs_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_batch_items ADD CONSTRAINT cms_ai_batch_items_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_batch_jobs ADD CONSTRAINT cms_ai_batch_jobs_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_entry_digests ADD CONSTRAINT cms_ai_entry_digests_entry_id_key UNIQUE (entry_id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_entry_digests ADD CONSTRAINT cms_ai_entry_digests_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_memory ADD CONSTRAINT cms_ai_memory_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_prices ADD CONSTRAINT cms_ai_prices_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_reviews ADD CONSTRAINT cms_ai_reviews_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_session_turns ADD CONSTRAINT cms_ai_session_turns_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_sessions ADD CONSTRAINT cms_ai_sessions_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_workflow_runs ADD CONSTRAINT cms_workflow_runs_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_workflow_steps ADD CONSTRAINT cms_workflow_steps_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_workflows ADD CONSTRAINT cms_workflows_pkey PRIMARY KEY (id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_batch_items ADD CONSTRAINT uq_batch_item_seq UNIQUE (job_id, seq); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_workflow_steps ADD CONSTRAINT uq_wf_step_node UNIQUE (run_id, node_id); EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "CREATE INDEX IF NOT EXISTS ix_ai_ab_site_time ON public.cms_ai_ab_runs USING btree (site_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_ai_reviews_entry ON public.cms_ai_reviews USING btree (entry_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_ai_reviews_model ON public.cms_ai_reviews USING btree (model, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_ai_reviews_site_time ON public.cms_ai_reviews USING btree (site_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_batch_items_job_status ON public.cms_ai_batch_items USING btree (job_id, status, seq)",
    "CREATE INDEX IF NOT EXISTS ix_batch_items_site ON public.cms_ai_batch_items USING btree (site_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_batch_jobs_site ON public.cms_ai_batch_jobs USING btree (site_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_cms_ai_digests_site ON public.cms_ai_entry_digests USING btree (site_id, built_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_cms_ai_digests_topics ON public.cms_ai_entry_digests USING gin (topics)",
    "CREATE INDEX IF NOT EXISTS ix_cms_ai_memory_site ON public.cms_ai_memory USING btree (site_id, status, enabled, scope, weight DESC)",
    "CREATE INDEX IF NOT EXISTS ix_cms_ai_prices_enabled ON public.cms_ai_prices USING btree (enabled)",
    "CREATE INDEX IF NOT EXISTS ix_cms_ai_sessions_entry ON public.cms_ai_sessions USING btree (entry_id)",
    "CREATE INDEX IF NOT EXISTS ix_cms_ai_sessions_updated ON public.cms_ai_sessions USING btree (updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_cms_ai_turns_session ON public.cms_ai_session_turns USING btree (session_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_cms_wf_runs_wf ON public.cms_workflow_runs USING btree (workflow_id, id DESC)",
    "CREATE INDEX IF NOT EXISTS ix_cms_wf_steps_run ON public.cms_workflow_steps USING btree (run_id, seq)",
    "CREATE INDEX IF NOT EXISTS ix_cms_workflows_next ON public.cms_workflows USING btree (next_run_at) WHERE (((trigger_type)::text = 'schedule'::text) AND ((status)::text = 'active'::text))",
    "CREATE INDEX IF NOT EXISTS ix_cms_workflows_site ON public.cms_workflows USING btree (site_id, status)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_batch_jobs_one_running ON public.cms_ai_batch_jobs USING btree (site_id) WHERE ((status)::text = 'running'::text)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_ai_memory_key ON public.cms_ai_memory USING btree (site_id, scope, key) WHERE ((key)::text <> ''::text)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_ai_prices ON public.cms_ai_prices USING btree (provider, model, kind)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cms_ai_sessions_key ON public.cms_ai_sessions USING btree (session_key)",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_batch_items ADD CONSTRAINT cms_ai_batch_items_entry_id_fkey FOREIGN KEY (entry_id) REFERENCES public.cms_entries(id) ON DELETE SET NULL; EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_batch_items ADD CONSTRAINT cms_ai_batch_items_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.cms_ai_batch_jobs(id) ON DELETE CASCADE; EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_batch_jobs ADD CONSTRAINT cms_ai_batch_jobs_content_type_id_fkey FOREIGN KEY (content_type_id) REFERENCES public.cms_content_types(id) ON DELETE RESTRICT; EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_batch_jobs ADD CONSTRAINT cms_ai_batch_jobs_site_id_fkey FOREIGN KEY (site_id) REFERENCES public.cms_sites(id) ON DELETE RESTRICT; EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_entry_digests ADD CONSTRAINT cms_ai_entry_digests_entry_id_fkey FOREIGN KEY (entry_id) REFERENCES public.cms_entries(id) ON DELETE CASCADE; EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_memory ADD CONSTRAINT cms_ai_memory_site_id_fkey FOREIGN KEY (site_id) REFERENCES public.cms_sites(id) ON DELETE CASCADE; EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_reviews ADD CONSTRAINT cms_ai_reviews_entry_id_fkey FOREIGN KEY (entry_id) REFERENCES public.cms_entries(id) ON DELETE SET NULL; EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_ai_session_turns ADD CONSTRAINT cms_ai_session_turns_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.cms_ai_sessions(id) ON DELETE CASCADE; EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_workflow_runs ADD CONSTRAINT cms_workflow_runs_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.cms_workflows(id) ON DELETE CASCADE; EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_workflow_steps ADD CONSTRAINT cms_workflow_steps_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.cms_workflow_runs(id) ON DELETE CASCADE; EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
    "DO $do$ BEGIN ALTER TABLE ONLY public.cms_workflows ADD CONSTRAINT cms_workflows_site_id_fkey FOREIGN KEY (site_id) REFERENCES public.cms_sites(id) ON DELETE CASCADE; EXCEPTION WHEN duplicate_object THEN NULL; WHEN duplicate_table THEN NULL; WHEN invalid_table_definition THEN NULL; WHEN unique_violation THEN NULL; END $do$",
]


def upgrade() -> None:
    """建 12 张 AI 表。已存在的对象全部跳过，不触碰任何既有数据。"""
    bind = op.get_bind()
    for stmt in _STATEMENTS:
        bind.exec_driver_sql(stmt)


def downgrade() -> None:
    """回滚只删本迁移建的表；CASCADE 会连带序列与索引。"""
    bind = op.get_bind()
    for table in reversed(_TABLES):
        bind.exec_driver_sql(f"DROP TABLE IF EXISTS public.{table} CASCADE")
