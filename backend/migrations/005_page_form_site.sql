-- 005: 补齐 pages/forms 的站内唯一约束 + 站点域名唯一
-- 幂等，可重复执行
BEGIN;

-- pages：001 已建 uq_pages_site_key，清掉遗留的全局 key 唯一
ALTER TABLE cms_pages DROP CONSTRAINT IF EXISTS cms_pages_key_key;

-- forms：原来 key 是全局唯一，站群下各站要用同名表单（contact 之类），改站内唯一
ALTER TABLE cms_forms DROP CONSTRAINT IF EXISTS cms_forms_key_key;
ALTER TABLE cms_forms DROP CONSTRAINT IF EXISTS uq_forms_site_key;
ALTER TABLE cms_forms ADD CONSTRAINT uq_forms_site_key UNIQUE (site_id, key);

-- 域名大小写不敏感唯一：一个域名只能指向一个站
DROP INDEX IF EXISTS uq_sites_domain;
CREATE UNIQUE INDEX uq_sites_domain ON cms_sites (lower(domain)) WHERE domain IS NOT NULL;

COMMIT;
