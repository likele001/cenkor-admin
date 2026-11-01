# 内容标签

取内容数据的四个 API：`content_list`、`content`、`related`、`search`。
全部只读、绑定当前站点。教程级的完整实战看[主题模板开发](/cenkor-admin/template-guide)。

## `content_list(...)` — 条目列表

```jinja
{% for r in content_list('article', limit=6, category='news') %}
  {% include "partials/card.html" %}
{% endfor %}
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `type` | `'article'` | `article` / `product` / `news` / `case`，或任意内容类型的 key |
| `limit` | `20` | 上限 **100** |
| `offset` | `0` | 跳过条数 |
| `category` | `None` | 分类 slug |
| `tag` | `None` | 标签 slug（仅 article） |
| `sort` | `'-published_at'` | 前缀 `-` 表示倒序；可选 `published_at`、`updated_at`、`created_at`、`sort`、`view_count`、`id` |
| `exclude` | `None` | 排除某条 id（做「相关推荐」用） |

### 返回字段（卡片）

`id`、`type`、`slug`、`title`、`excerpt`、`cover`、`url`、`published_at`、`updated_at`、
`view_count`、`sort`、`ai_generated`、`content`、`custom_fields`、`seo`、`category`、`tags`。

> `product` 读的是产品目录表，卡片字段不同（`is_flagship`、`github_url`、`demo_url` 等）；
> `article` / `news` / `case` 读同一套内容引擎，卡片**完全同构**，可以共用一套卡片模板。
> 卡片里的 `type` 是条目自己的类型，`url` 也按它拼 —— `/news/` 列表里的卡片
> 不会错误地指向 `/article/`。

## `content(type, slug)` — 单条详情

```jinja
{% set it = content('article', 'my-post') %}
{% if it %}
  <h2>{{ it.title }}</h2>
  {{ it.body_html|safe }}
{% endif %}
```

返回和 `content_list` 卡片同构，**额外带 `body_html`**。查不到返回 `None`，先判空再取字段。

## `related(item, limit=4)` — 相关推荐

同分类优先，不够时用同类型最新补齐，已排除自己。`limit` 上限 12。

```jinja
{% if item %}
  <h3>相关内容</h3>
  {% for r in related(item, 3) %}
    {% include "partials/card.html" %}
  {% endfor %}
{% endif %}
```

## `search(kw, limit=20, page=1)` — 站内搜索

```jinja
{% set res = search(request_kw) %}
<p>共 {{ res.total }} 条</p>
{% for r in res.items %}
  {% include "partials/card.html" %}
{% endfor %}
```

返回结构：`items`、`total`、`page`、`per_page`、`total_pages`、`kw`。
`limit` 上限 50。`kw` 为空时返回空结果，不报错。当前匹配标题和 slug。

搜索页拿关键词用 `page.pagination` 配合 `url('search')`，参见[站点与配置](/cenkor-admin/template/config)。

## `item` 对象字段表（详情页）

详情页渲染时注入的 `item`，列表页为 `None`：

| 字段 | 说明 |
|---|---|
| `item.id` / `item.slug` / `item.title` | 基本信息 |
| `item.body_html` | **正文 HTML，必须 `\|safe`**，否则会被转义成一堆 `&lt;p&gt;` |
| `item.excerpt` | 摘要（纯文本） |
| `item.cover` | 封面**绝对地址**，可能为空串 |
| `item.seo` | 原始 SEO 字典：`seo.title` / `seo.description` / `seo.og_image` |
| `item.content` | 原始内容字典，字段随内容类型而不同：`content.text` / `content.cover_image` / `content.tagline` 等 |
| `item.custom_fields` | 自定义字段字典 |
| `item.category` | `{id, slug, name, url}` 或 `None` |
| `item.tags` | 标签**名称**数组，如 `["智能制造", "案例"]`（不是对象） |
| `item.published_at` / `item.updated_at` | datetime 或 `None`，配合 `|date` 过滤 |
| `item.view_count` | 阅读数 |
| `item.ai_generated` | bool |

`article` 之外的 `kind`（product / news / case）字段是各自表结构的投影，
`item.content` 里放该类型专有字段：产品有 `content.tagline` / `content.features`，
案例有 `content.industry` / `content.desc`。

> `item` 里没有 `status`、`site_id` 这类内部敏感字段，也没有 ORM 对象 —— 全是普通 dict。
