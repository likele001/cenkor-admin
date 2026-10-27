-- CMS AI 层 · 幂等建表脚本
--
-- 为什么不走 alembic：
-- 这些表属于公开模块，但当前迁移链尾是闭源 revision（0100_app_schema）。
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

-- ---- 后台可视化配置：服务商通道与能力绑定 ----
-- 密钥列存 Fernet 密文（前缀 enc:v1:），明文只在内存里出现；
-- api_key_hint 存末四位掩码，列表页零解密即可展示。

CREATE TABLE IF NOT EXISTS cms_ai_providers (
    id              SERIAL PRIMARY KEY,
    slug            VARCHAR(64)  NOT NULL UNIQUE,
    name            VARCHAR(80)  NOT NULL,
    kind            VARCHAR(32)  NOT NULL DEFAULT 'openai',
    base_url        VARCHAR(400) NOT NULL,
    api_key_enc     TEXT         NOT NULL DEFAULT '',
    api_key_hint    VARCHAR(16)  NOT NULL DEFAULT '',
    extra_headers   JSONB,
    timeout_seconds INTEGER      NOT NULL DEFAULT 60,
    max_retries     INTEGER      NOT NULL DEFAULT 2,
    enabled         BOOLEAN      NOT NULL DEFAULT TRUE,
    remark          VARCHAR(255),
    last_test_at    TIMESTAMPTZ,
    last_test_ok    BOOLEAN,
    last_test_error TEXT,
    is_builtin      BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_by      INTEGER
);

CREATE INDEX IF NOT EXISTS ix_cms_ai_providers_enabled ON cms_ai_providers (enabled);

CREATE TABLE IF NOT EXISTS cms_ai_capabilities (
    capability  VARCHAR(32) PRIMARY KEY,
    provider_id INTEGER REFERENCES cms_ai_providers(id) ON DELETE RESTRICT,
    model       VARCHAR(160) NOT NULL DEFAULT '',
    params      JSONB,
    enabled     BOOLEAN      NOT NULL DEFAULT TRUE,
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_by  INTEGER
);

CREATE INDEX IF NOT EXISTS ix_cms_ai_capabilities_provider_id
    ON cms_ai_capabilities (provider_id);
