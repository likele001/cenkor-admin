-- CMS AI 层 · 幂等建表脚本
--
-- 为什么不走 alembic：
-- 这两张表属于公开模块，但当前迁移链尾是闭源 revision（0100_app_schema）。
-- 挂到链尾 → 公开仓库单独建图找不到 parent；插到公开链中间 → 生产已越过该点，
-- alembic 不会回头执行。所以采用项目已有的「应用自带 schema」哲学：
-- 启动时幂等执行，由 app_schema_versions 记录版本。
--
-- 铁律：本文件必须完全幂等。只允许 CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS，
-- 不允许 DROP / ALTER（列变更请另开迁移脚本并在 bootstrap 里判定版本）。

CREATE TABLE IF NOT EXISTS cms_embeddings (
    id            SERIAL PRIMARY KEY,
    entry_id      INTEGER      NOT NULL REFERENCES cms_entries(id) ON DELETE CASCADE,
    field         VARCHAR(40)  NOT NULL DEFAULT 'combined',
    lang          VARCHAR(16)  NOT NULL DEFAULT 'base',
    vector        DOUBLE PRECISION[],
    dim           INTEGER      NOT NULL DEFAULT 0,
    content_hash  VARCHAR(64)  NOT NULL DEFAULT '',
    model         VARCHAR(80)  NOT NULL DEFAULT '',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_cms_embedding_target UNIQUE (entry_id, field, lang)
);

CREATE INDEX IF NOT EXISTS ix_cms_embeddings_entry_id ON cms_embeddings (entry_id);
CREATE INDEX IF NOT EXISTS ix_cms_embeddings_model ON cms_embeddings (model);

CREATE TABLE IF NOT EXISTS cms_ai_generations (
    id             SERIAL PRIMARY KEY,
    kind           VARCHAR(40) NOT NULL,
    target         VARCHAR(80) NOT NULL DEFAULT '',
    provider       VARCHAR(40) NOT NULL DEFAULT '',
    model          VARCHAR(80) NOT NULL DEFAULT '',
    prompt_digest  VARCHAR(64) NOT NULL DEFAULT '',
    params         JSONB,
    tokens_in      INTEGER     NOT NULL DEFAULT 0,
    tokens_out     INTEGER     NOT NULL DEFAULT 0,
    latency_ms     INTEGER     NOT NULL DEFAULT 0,
    status         VARCHAR(20) NOT NULL DEFAULT 'ok',
    error          TEXT,
    created_by     INTEGER,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_cms_ai_generations_kind ON cms_ai_generations (kind);
CREATE INDEX IF NOT EXISTS ix_cms_ai_generations_status ON cms_ai_generations (status);
CREATE INDEX IF NOT EXISTS ix_cms_ai_generations_created_at ON cms_ai_generations (created_at);
CREATE INDEX IF NOT EXISTS ix_cms_ai_gen_target ON cms_ai_generations (kind, target);
