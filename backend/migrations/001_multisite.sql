-- 多站点/站群地基：cms_sites + 各内容表 site_id
-- 幂等，可重复执行

BEGIN;

CREATE TABLE IF NOT EXISTS cms_sites (
  id            serial PRIMARY KEY,
  key           varchar(64)  NOT NULL UNIQUE,
  name          varchar(120) NOT NULL,
  kind          varchar(20)  NOT NULL DEFAULT 'main',
  domain        varchar(255),
  locale        varchar(20)  NOT NULL DEFAULT 'zh-CN',
  default_lang  varchar(20),
  site_mode     varchar(20)  NOT NULL DEFAULT 'article',
  geo           jsonb,
  seo_defaults  jsonb,
  settings      jsonb,
  status        varchar(20)  NOT NULL DEFAULT 'active',
  sort          int          NOT NULL DEFAULT 0,
  created_at    timestamptz  NOT NULL DEFAULT now(),
  updated_at    timestamptz  NOT NULL DEFAULT now()
);

INSERT INTO cms_sites (key, name, kind, site_mode, sort)
VALUES ('main', '主站', 'main', 'article', 0)
ON CONFLICT (key) DO NOTHING;

-- ---------- entries ----------
ALTER TABLE cms_entries ADD COLUMN IF NOT EXISTS site_id integer NOT NULL DEFAULT 1;
ALTER TABLE cms_entries DROP CONSTRAINT IF EXISTS uq_entry_ct_slug;
ALTER TABLE cms_entries DROP CONSTRAINT IF EXISTS uq_entry_site_ct_slug;
ALTER TABLE cms_entries ADD CONSTRAINT uq_entry_site_ct_slug UNIQUE (site_id, content_type_id, slug);
ALTER TABLE cms_entries DROP CONSTRAINT IF EXISTS fk_entries_site;
ALTER TABLE cms_entries ADD CONSTRAINT fk_entries_site FOREIGN KEY (site_id) REFERENCES cms_sites(id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS idx_entries_site_status ON cms_entries (site_id, status);
CREATE INDEX IF NOT EXISTS idx_entries_site_ct ON cms_entries (site_id, content_type_id);

-- ---------- categories ----------
ALTER TABLE cms_categories ADD COLUMN IF NOT EXISTS site_id integer NOT NULL DEFAULT 1;
ALTER TABLE cms_categories DROP CONSTRAINT IF EXISTS uq_category_ct_slug;
ALTER TABLE cms_categories DROP CONSTRAINT IF EXISTS uq_category_site_ct_slug;
ALTER TABLE cms_categories ADD CONSTRAINT uq_category_site_ct_slug UNIQUE (site_id, content_type_id, slug);
ALTER TABLE cms_categories DROP CONSTRAINT IF EXISTS fk_categories_site;
ALTER TABLE cms_categories ADD CONSTRAINT fk_categories_site FOREIGN KEY (site_id) REFERENCES cms_sites(id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS idx_categories_site ON cms_categories (site_id);

-- ---------- tags ----------
ALTER TABLE cms_tags ADD COLUMN IF NOT EXISTS site_id integer NOT NULL DEFAULT 1;
ALTER TABLE cms_tags DROP CONSTRAINT IF EXISTS fk_tags_site;
ALTER TABLE cms_tags ADD CONSTRAINT fk_tags_site FOREIGN KEY (site_id) REFERENCES cms_sites(id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS idx_tags_site ON cms_tags (site_id);

-- ---------- media ----------
ALTER TABLE cms_media ADD COLUMN IF NOT EXISTS site_id integer NOT NULL DEFAULT 1;
ALTER TABLE cms_media DROP CONSTRAINT IF EXISTS fk_media_site;
ALTER TABLE cms_media ADD CONSTRAINT fk_media_site FOREIGN KEY (site_id) REFERENCES cms_sites(id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS idx_media_site ON cms_media (site_id);

-- ---------- pages ----------
ALTER TABLE cms_pages ADD COLUMN IF NOT EXISTS site_id integer NOT NULL DEFAULT 1;
ALTER TABLE cms_pages DROP CONSTRAINT IF EXISTS cms_pages_key_key;
ALTER TABLE cms_pages DROP CONSTRAINT IF EXISTS uq_pages_site_key;
ALTER TABLE cms_pages ADD CONSTRAINT uq_pages_site_key UNIQUE (site_id, key);
ALTER TABLE cms_pages DROP CONSTRAINT IF EXISTS fk_pages_site;
ALTER TABLE cms_pages ADD CONSTRAINT fk_pages_site FOREIGN KEY (site_id) REFERENCES cms_sites(id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS idx_pages_site ON cms_pages (site_id);

-- ---------- forms ----------
ALTER TABLE cms_forms ADD COLUMN IF NOT EXISTS site_id integer NOT NULL DEFAULT 1;
ALTER TABLE cms_forms DROP CONSTRAINT IF EXISTS fk_forms_site;
ALTER TABLE cms_forms ADD CONSTRAINT fk_forms_site FOREIGN KEY (site_id) REFERENCES cms_sites(id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS idx_forms_site ON cms_forms (site_id);

-- ---------- legacy ----------
ALTER TABLE cms_news     ADD COLUMN IF NOT EXISTS site_id integer NOT NULL DEFAULT 1;
ALTER TABLE cms_products ADD COLUMN IF NOT EXISTS site_id integer NOT NULL DEFAULT 1;
ALTER TABLE cms_cases    ADD COLUMN IF NOT EXISTS site_id integer NOT NULL DEFAULT 1;
CREATE INDEX IF NOT EXISTS idx_news_site     ON cms_news (site_id);
CREATE INDEX IF NOT EXISTS idx_products_site ON cms_products (site_id);
CREATE INDEX IF NOT EXISTS idx_cases_site    ON cms_cases (site_id);

COMMIT;
