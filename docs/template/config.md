# 站点与配置

站点信息、页面元信息、URL 生成、分页、静态资源。

## `site` — 站点信息（预注入 dict）

不是函数，渲染时直接就在：

```jinja
{{ site.name }}
{{ site['brand.name'] }}
{{ site['brand.description'] }}
{{ site.locale or 'zh-CN' }}
```

内容由五部分拼成：站点基础字段（`id`、`key`、`name`、`kind`、`domain`、`locale`、
`site_mode`、`geo`）+ 站点设置（原样平铺，所以有 `brand.name` 这种带点的 key）
+ SEO 默认值（前缀成 `seo.xxx`）+ 站点配置表键值 + `base_url`。

> **带点的 key 必须用方括号**：`site['brand.name']`。
> 写成 `site.brand.name` 会去找 `brand` 这个键，拿不到东西。

### `site_meta(key=None)`

取单个站点配置，不传 `key` 返回整个 dict（和 `site` 一样）。`site` 已预注入，一般不用这个。

```jinja
{{ site_meta('brand.name') }}
```

## `page` 对象 — 页面元信息

| 字段 | 说明 |
|---|---|
| `page.kind` | `article` / `product` / `news` / `case` / `page` |
| `page.title` | 内容标题（不含站点名） |
| `page.full_title` | `标题 · 站点名`，`<title>` 用这个 |
| `page.description` | 描述，SEO 与卡片摘要共用 |
| `page.canonical` | 规范链接（绝对地址） |
| `page.base` | 站点根地址 |
| `page.site_name` / `page.site_desc` | 站点名 / 站点描述 |
| `page.og.type` | OG 类型，等于 `kind` |
| `page.og.site_name` / `page.og.title` / `page.og.description` / `page.og.url` | OG 四件套 |
| `page.og.image` | 封面绝对地址，可能为空串 |
| `page.og.video` | 正文里第一个 `<video>` 的地址，没有为空串 |
| `page.json_ld` | 已序列化的 JSON-LD 字符串，用 `\|safe` 放进 `<script type="application/ld+json">` |
| `page.published_at` | ISO 时间字符串，可能为 `None` |
| `page.published_text` | `YYYY-MM-DD`，可能为空串 |
| `page.updated_at` | ISO 时间字符串，可能为 `None` |
| `page.ai_origin` | AI 生成溯源，人工写的为 `None` |
| `page.item` | 同顶层 `item` |
| `page.items` | 同顶层 `items`（注意 `page.items` 撞 dict 方法，用顶层 `items`） |
| `page.pagination` | 列表页是真实分页对象，详情页为 `None` |

layout 里的标准用法：

```jinja
<title>{{ page.full_title }}</title>
<link rel="canonical" href="{{ page.canonical }}">
<meta property="og:title" content="{{ page.og.title }}">
<meta property="og:image" content="{{ page.og.image }}">
<script type="application/ld+json">{{ page.json_ld|safe }}</script>
```

## `url(kind='home', slug=None, page=None)` — 生成链接

按站点 URL 规则拼链接，别在模板里手拼字符串（改 URL 规则后手拼的全失效）。

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

传 `page=` 时，列表类生成路径式分页 `/article/page/2/`；`search` 仍是 `&page=N`。
详情页传 `page=` 会被忽略。

```jinja
<a href="{{ url('home') }}">首页</a>
<a href="{{ url('category', 'news') }}">新闻</a>
<a href="{{ url('article', r.slug) }}">{{ r.title }}</a>
```

## `pagination(...)` — 分页对象

返回结构：

```
{page, per_page, total, total_pages,
 window: [页码数组], has_prev, has_next, prev_page, next_page,
 range_start, range_end,
 # 下面五个只有传了 base_path 才有值，否则是 None：
 url, first_url, last_url, prev_url, next_url,
 pages: [{n, url, current}, ...]}
```

- **列表页直接用预注入的 `pagination`**，路由已经填好 `base_path`。
- 自己调 `pagination(1, 128, 12, 5, '/article/')` 时，`base_path` 传列表基路径，
  生成的链接是**绝对地址**，可直接当 `href`。
- `window` 是当前显示的页码数组，直接循环。`page` 会被夹到 `[1, total_pages]`。

```jinja
{% if pagination.has_prev %}<a href="{{ pagination.prev_url }}">上一页</a>{% endif %}

{% for p in pagination.pages %}
  <a href="{{ p.url }}" {% if p.current %}class="on"{% endif %}>{{ p.n }}</a>
{% endfor %}

{% if pagination.has_next %}<a href="{{ pagination.next_url }}">下一页</a>{% endif %}
```

## `asset(path='')` — 静态资源地址

绝对 URL（`http://`、`https://`、`//`、`data:`）原样返回；相对路径拼站点根。
不传参数返回站点根 + `/`。

```jinja
<link rel="stylesheet" href="{{ asset('assets/style.css') }}">
<img src="{{ asset('/static/logo.png') }}" alt="{{ site.name }}">
```

过滤器形式 `|asset_url` 同效，空值返回空串，适合封面可能为空的场景：

```jinja
{% if item.cover %}<img src="{{ item.cover|asset_url }}" alt="{{ item.title }}">{% endif %}
```

## 其余预注入变量

| 变量 | 说明 |
|---|---|
| `base_url` | 站点根地址，如 `https://www.cenkor.cn`，无尾斜杠 |
| `theme_css` | 主题 `assets/style.css` 内容，加 `\|safe` 放进 `<style>` 标签输出 |
| `theme_name` | 当前主题名 |
| `now` | 渲染时刻，配合 `|date` |

```jinja
<footer>© {{ now|date('%Y') }} {{ site.name }}</footer>
```
