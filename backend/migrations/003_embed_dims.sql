-- embedding 能力降到 1024 维（pgvector HNSW 索引上限 2000）
-- 注意：params 列存的是 jsonb 的 'null' 值，不是 SQL NULL，
-- 所以 COALESCE 不生效，直接 || 会拼成 [null, {...}] 这种数组。必须按类型判断。
UPDATE cms_ai_capabilities
SET params = CASE
    WHEN params IS NULL
      OR jsonb_typeof(params) IS NULL
      OR jsonb_typeof(params) <> 'object'
    THEN '{"dimensions": 1024}'::jsonb
    ELSE params || '{"dimensions": 1024}'::jsonb
END
WHERE capability = 'embedding';

SELECT capability, model, params FROM cms_ai_capabilities;
