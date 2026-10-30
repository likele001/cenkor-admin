-- cms_embeddings.vector: double precision[] -> pgvector vector(1024) + HNSW 索引
-- 旧向量是 2048 维（豆包默认），装不进 1024 维列，只能清空后由应用重建。
-- 幂等，可重复执行。

BEGIN;

DROP INDEX IF EXISTS ix_cms_embeddings_hnsw;
DELETE FROM cms_embeddings;
ALTER TABLE cms_embeddings DROP COLUMN IF EXISTS vector;
ALTER TABLE cms_embeddings ADD COLUMN vector vector(1024);

-- HNSW：余弦距离。1024 维在上限 2000 以内，可以建索引。
CREATE INDEX ix_cms_embeddings_hnsw
  ON cms_embeddings USING hnsw (vector vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

COMMENT ON COLUMN cms_embeddings.vector IS
  'pgvector 向量，1024 维（豆包 dimensions=1024）；HNSW 余弦索引';

COMMIT;
