-- 补充 001：cms_tags 跨站唯一约束
-- 001 只加了 site_id 列，漏了把 uq_tag_ct_slug 升级为带 site_id 的版本
-- 幂等，可重复执行

BEGIN;

ALTER TABLE cms_tags DROP CONSTRAINT IF EXISTS uq_tag_ct_slug;
ALTER TABLE cms_tags DROP CONSTRAINT IF EXISTS uq_tag_site_ct_slug;
ALTER TABLE cms_tags ADD CONSTRAINT uq_tag_site_ct_slug
  UNIQUE (site_id, content_type_id, slug);

COMMIT;
