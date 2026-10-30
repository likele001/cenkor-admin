-- 提示词版本化：cms_ai_prompts
-- 幂等，可重复执行
--
-- 设计要点：
-- 1. (prompt_key, version) 唯一 —— 版本单调递增，历史永久保留，可对比可回滚
-- 2. is_active 部分唯一索引 —— 每个 key 同时只有一个生效版本，
--    靠 DB 保证而不是靠应用层自觉（并发激活两个版本会直接失败）
-- 3. content 非空 CHECK —— 空提示词会让模型行为完全失控，挡在入口

BEGIN;

CREATE TABLE IF NOT EXISTS cms_ai_prompts (
  id          serial       PRIMARY KEY,
  prompt_key  varchar(64)  NOT NULL,
  version     int          NOT NULL DEFAULT 1,
  content     text         NOT NULL,
  note        varchar(255),
  is_active   boolean      NOT NULL DEFAULT false,
  created_by  int,
  created_at  timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_prompts_key ON cms_ai_prompts (prompt_key);

ALTER TABLE cms_ai_prompts DROP CONSTRAINT IF EXISTS uq_ai_prompt_key_ver;
ALTER TABLE cms_ai_prompts ADD CONSTRAINT uq_ai_prompt_key_ver UNIQUE (prompt_key, version);

-- 每个 key 只能有一个激活版本
DROP INDEX IF EXISTS uq_ai_prompt_active;
CREATE UNIQUE INDEX uq_ai_prompt_active ON cms_ai_prompts (prompt_key) WHERE is_active;

ALTER TABLE cms_ai_prompts DROP CONSTRAINT IF EXISTS ck_ai_prompt_nonempty;
ALTER TABLE cms_ai_prompts ADD CONSTRAINT ck_ai_prompt_nonempty
  CHECK (length(btrim(content)) > 0);

COMMIT;
