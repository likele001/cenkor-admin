# 站点与配置

站点信息、页面元信息、URL 生成、分页、静态资源。
每个标签统一按 **语法 → 参数 → 返回 → 示例** 四段说明。

## `site` — 站点信息（预注入 dict）

不是函数，渲染时直接就在。

**语法**

```jinja
{{ site.name }}
{{ site['brand.name'] }}
```

**参数**

无（预注入 dict）。取值用点号；**带点的 key 必须用方括号**：`site['brand.name']`，
写成 `site.brand.name` 会去找 `brand` 这个键，拿不到东西。

**返回**

由五部分拼成的 dict：

```text
{
  "id": 1, "key": "www", "name": "站点名", "kind": "...",
  "domain": "...", "locale": "zh-CN", "site_mode": "...", "geo": "...",
  "brand.name": "...",          // 站点设置原样平铺，会出现带点的 key
  "seo.title": "...",           // SEO 默认值，前缀成 seo.xxx
  "其他站点配置键值": "...",
  "base_url": "https://www.cenkor.cn"
}
```

**示例**

```jinja
{{ site.name }}
{{ site['brand.description'] }}
{{ site.locale or 'zh-CN' }}
```

## `site_meta(key=None)` — 取单个站点配置

**语法**

```jinja
{{ site_meta('brand.name') }}
```

**参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `key` | str | `None` | 配置键；不传返回整个 dict（和 `site` 一样） |

**返回**

配置值（str / dict 视键而定）。`site` 已预注入，一般不用这个。

**示例**

```jinja
{{ site_meta('brand.name') }}
```

## `page` 对象 — 页面元信息

预注入 dict，不是函数。

**语法**

```jinja
{{ page.full_title }}
```

**返回**

```text
{
  "kind": "article | product | news | case | page",
  "title": "内容标题（不含站点名）",
  "full_title": "标题 · 站点名",
  "description": "描述，SEO 与卡片摘要共用",
  "canonical": "规范链接（绝对地址）",
  "base": "站点根地址",
  "site_name": "站点名", "site_desc": "站点描述",
  "og": {
    "type": "等于 kind", "site_name": "...", "title": "...",
    "description": "...", "url": "...",
    "image": "封面绝对地址，可能为空串",
    "video": "正文里第一个 <video> 的地址，没有为空串"
  },
  "json_ld": "已序列化的 JSON-LD 字符串，必须 |safe 放进 <script>",
  "published_at": "ISO 时间字符串或 null",
  "published_text": "YYYY-MM-DD 或空串",
  "updated_at": "ISO 时间字符串或 null",
  "ai_origin": "AI 生成溯源，人工写的为 null",
  "item": "同顶层 item",
  "items": "同顶层 items（注意 page.items 撞 dict 方法，用顶层 items）",
  "pagination": "列表页是真实分页对象，详情页为 null"
}
```

**示例**

layout 里的标准头部：

```jinja
<title>{{ page.full_title }}</title>
<link rel="canonical" href="{{ page.canonical }}">
<meta property="og:title" content="{{ page.og.title }}">
<meta property="og:image" content="{{ page.og.image }}">
<script type="application/ld+json">{{ page.json_ld|safe }}</script>
```

## `url(kind='home', slug=None, page=None)` — 生成链接

按站点 URL 规则拼链接。别在模板里手拼字符串 —— 改 URL 规则后手拼的全失效。

**语法**

```jinja
<a href="{{ url('article', r.slug) }}">{{ r.title }}</a>
```

**参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `kind` | str | `'home'` | 见下表 |
| `slug` | str | `None` | 条目 / 分类 / 标签的 slug |
| `page` | int | `None` | 页码，仅列表类生效 |

`kind` 对照：

| `kind` | 结果 |
|---|---|
| `home` | `/` |
| `search` | `/search/?kw=...` |
| `category` | `/category/{slug}/` |
| `tag` | `/tag/{slug}/` |
| `article` | `/article/{slug}.html` |
| `product` | `/product/{slug}.html` |
| `news` | `/news/{slug}.html` |
| `case` | `/case/{slug}.html` |
| `page` | `/p/{slug}.html` |
| 其它 | 按 `article` 处理 |

**返回**

URL 字符串。传 `page=` 时，列表类生成路径式分页 `/article/page/2/`；
`search` 仍是 `&page=N`。详情页传 `page=` 会被忽略。

**示例**

```jinja
<a href="{{ url('home') }}">首页</a>
<a href="{{ url('category', 'news') }}">新闻</a>
<a href="{{ url('article', r.slug) }}">{{ r.title }}</a>
```

## `pagination(...)` — 分页对象

**语法**

列表页直接用预注入的 `pagination`（路由已填好 base_path）；
自己拼区块时才手动调用：

```jinja
{% set pg = pagination(1, 128, 12, 5, '/article/') %}
```

**参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `page` | int | `1` | 当前页，自动夹到 `[1, total_pages]` |
| `total` | int | `0` | 总条数 |
| `per_page` | int | `20` | 每页条数 |
| `window` | int | `5` | 显示几个页码 |
| `base_path` | str | `None` | 列表基路径；传了才生成 URL 字段 |

**返回**

```text
{
  "page": 1, "per_page": 20, "total": 0, "total_pages": 0,
  "window": [1, 2, 3, 4, 5],
  "has_prev": false, "has_next": true, "prev_page": null, "next_page": 2,
  "range_start": 1, "range_end": 20,
  "url": null, "first_url": null, "last_url": null,
  "prev_url": null, "next_url": null,      // 这五个只有传了 base_path 才有值
  "pages": [ { "n": 1, "url": "...", "current": true }, ... ]
}
```

传了 `base_path` 生成的链接是**绝对地址**，可直接当 `href`。

**示例**

```jinja
{% if pagination.has_prev %}<a href="{{ pagination.prev_url }}">上一页</a>{% endif %}

{% for p in pagination.pages %}
  <a href="{{ p.url }}" {% if p.current %}class="on"{% endif %}>{{ p.n }}</a>
{% endfor %}

{% if pagination.has_next %}<a href="{{ pagination.next_url }}">下一页</a>{% endif %}
```

## `asset(path='')` — 静态资源地址

**语法**

```jinja
<link rel="stylesheet" href="{{ asset('assets/style.css') }}">
```

**参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `path` | str | `''` | 相对路径拼站点根；不传返回站点根 + `/` |

**返回**

URL 字符串。绝对 URL（`http://`、`https://`、`//`、`data:`）原样返回。

**示例**

过滤器形式 `|asset_url` 同效，空值返回空串，适合封面可能为空的场景：

```jinja
<img src="{{ asset('/static/logo.png') }}" alt="{{ site.name }}">
{% if item.cover %}<img src="{{ item.cover|asset_url }}" alt="{{ item.title }}">{% endif %}
```

## 其余预注入变量

| 变量 | 类型 | 说明 |
|---|---|---|
| `base_url` | str | 站点根地址，无尾斜杠 |
| `theme_css` | str | 主题 `assets/style.css` 内容，加 `\|safe` 放进 `<style>` 标签输出 |
| `theme_name` | str | 当前主题名 |
| `now` | datetime | 渲染时刻，配合 `|date` |

**示例**

```jinja
<footer>© {{ now|date('%Y') }} {{ site.name }}</footer>
```
