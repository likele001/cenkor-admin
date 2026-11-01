# 内容标签

取内容数据的四个 API。全部只读、绑定当前站点。
每个标签统一按 **语法 → 参数 → 返回 → 示例** 四段说明。

## `content_list(...)` — 条目列表

**语法**

```jinja
{% for r in content_list('article', limit=6, category='news') %}
  {% include "partials/card.html" %}
{% endfor %}
```

**参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `type` | str | `'article'` | `article` / `product` / `news` / `case`，或任意内容类型的 key |
| `limit` | int | `20` | 上限 **100** |
| `offset` | int | `0` | 跳过条数 |
| `category` | str | `None` | 分类 slug |
| `tag` | str | `None` | 标签 slug（仅 article） |
| `sort` | str | `'-published_at'` | 前缀 `-` 表示倒序；可选 `published_at`、`updated_at`、`created_at`、`sort`、`view_count`、`id` |
| `exclude` | int | `None` | 排除某条 id（做「相关推荐」用） |

**返回**

卡片数组，每张卡片：

```text
{
  "id": 1, "type": "article", "slug": "my-post",
  "title": "标题",
  "excerpt": "摘要（纯文本）",
  "cover": "封面绝对地址，可能为空串",
  "url": "/article/my-post.html",
  "published_at": "datetime", "updated_at": "datetime",
  "view_count": 0, "sort": 0, "ai_generated": false,
  "content": { "该类型原始内容字典": "..." },
  "custom_fields": { },
  "seo": { "title": "", "description": "", "og_image": "" },
  "category": { "id": 1, "slug": "news", "name": "新闻", "url": "..." },
  "tags": ["标签名", "..."]
}
```

> `product` 读的是产品目录表，卡片字段不同（`is_flagship`、`github_url`、`demo_url` 等）；
> `article` / `news` / `case` 读同一套内容引擎，卡片**完全同构**，可共用一套卡片模板。
> 卡片里的 `type` 是条目自己的类型，`url` 也按它拼 —— `/news/` 列表里的卡片
> 不会错误地指向 `/article/`。

**示例**

首页「最新文章」区块：

```jinja
{% for r in content_list('article', limit=6) %}
  <article class="card">
    {% if r.cover %}<img src="{{ r.cover }}" alt="{{ r.title }}">{% endif %}
    <h3><a href="{{ r.url }}">{{ r.title }}</a></h3>
    <p>{{ r.excerpt|excerpt(80) }}</p>
    <time>{{ r.published_at|date('%Y-%m-%d') }}</time>
  </article>
{% endfor %}
```

## `content(type, slug)` — 单条详情

**语法**

```jinja
{% set it = content('article', 'my-post') %}
```

**参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `type` | str | `'article'` | 内容类型 key |
| `slug` | str | `''` | 条目 slug |

**返回**

和 `content_list` 卡片同构，**额外带 `body_html`**（正文 HTML）。
查不到返回 `None`，先判空再取字段。

**示例**

```jinja
{% set it = content('article', 'my-post') %}
{% if it %}
  <h2>{{ it.title }}</h2>
  {{ it.body_html|safe }}
{% endif %}
```

## `related(item, limit=4)` — 相关推荐

**语法**

```jinja
{% for r in related(item, 3) %} ... {% endfor %}
```

**参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `item` | dict | 必填 | 当前内容（详情页的 `item`） |
| `limit` | int | `4` | 上限 12 |

**返回**

卡片数组，同 `content_list`。同分类优先，不够时用同类型最新补齐，已排除自己。

**示例**

详情页底部「相关内容」：

```jinja
{% if item %}
  <h3>相关内容</h3>
  {% for r in related(item, 3) %}
    {% include "partials/card.html" %}
  {% endfor %}
{% endif %}
```

## `search(kw, limit=20, page=1)` — 站内搜索

**语法**

```jinja
{% set res = search(request_kw) %}
```

**参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `kw` | str | `''` | 关键词，为空返回空结果（不报错） |
| `limit` | int | `20` | 上限 50 |
| `page` | int | `1` | 页码 |

**返回**

```text
{
  "items": [ "卡片数组，同 content_list" ],
  "total": 0, "page": 1, "per_page": 20, "total_pages": 0,
  "kw": "搜索词"
}
```

当前匹配标题和 slug。

**示例**

```jinja
{% set res = search(request_kw) %}
<p>共 {{ res.total }} 条</p>
{% for r in res.items %}
  {% include "partials/card.html" %}
{% endfor %}
```

## `item` 对象 — 详情页当前内容

详情页渲染时注入的顶层变量，列表页为 `None`。不是函数，没有语法。

**返回**

```text
{
  "id": 1, "slug": "my-post", "title": "标题",
  "body_html": "正文 HTML —— 必须 |safe 输出",
  "excerpt": "摘要（纯文本）",
  "cover": "封面绝对地址，可能为空串",
  "seo": { "title": "", "description": "", "og_image": "" },
  "content": { "原始内容字典，字段随类型而不同": "..." },
  "custom_fields": { },
  "category": { "id": 1, "slug": "news", "name": "新闻", "url": "..." },
  "tags": ["标签名", "..."],
  "published_at": "datetime", "updated_at": "datetime",
  "view_count": 0, "ai_generated": false
}
```

> `article` 之外的 `kind`（product / news / case）字段是各自表结构的投影，
> `item.content` 里放该类型专有字段：产品有 `content.tagline` / `content.features`，
> 案例有 `content.industry` / `content.desc`。
> `item` 里没有 `status`、`site_id` 这类内部敏感字段，也没有 ORM 对象 —— 全是普通 dict。

**示例**

详情页主体：

```jinja
<article>
  <h1>{{ item.title }}</h1>
  <time>{{ item.published_at|date('%Y年%m月%d日') }}</time>
  {% if item.cover %}<img src="{{ item.cover }}" alt="{{ item.title }}">{% endif %}
  <div class="content">{{ item.body_html|safe }}</div>

  {% if item.tags %}
    <div class="tags">
      {% for name in item.tags %}<span>{{ name }}</span>{% endfor %}
    </div>
  {% endif %}
</article>
```

## 打印与调试

### 两种花括号

| 写法 | 干什么 | 例子 |
|---|---|---|
| `{% ... %}` | **逻辑**：循环、判断、赋值，不显示任何东西 | `{% for %}`、`{% if %}`、`{% set %}` |
| `{{ ... }}` | **打印**：把变量的值输出到页面 | `{{ r.title }}` |

### 传入参数 vs 返回数据

`content_list('article', limit=6, category='news')` 括号里是**筛选条件**，喂给函数的，不用打印。
函数返回一堆卡片，`for` 一轮轮拿，**每轮的 `r` 就是一条内容**，打印的是 `r` 的字段：

```jinja
{% for r in content_list('article', limit=6, category='news') %}
  <div class="card">
    <a href="{{ r.url }}">{{ r.title }}</a>
    <img src="{{ r.cover }}" alt="{{ r.title }}">
    <p>{{ r.excerpt|excerpt(80) }}</p>
    <time>{{ r.published_at|date('%Y-%m-%d') }}</time>
  </div>
{% endfor %}
```

### 一键打印全部字段

记不住字段名？`|json_safe` 把整条内容打成 JSON 直接看：

```jinja
{% for r in content_list('article', limit=2) %}
  <pre>{{ r|json_safe }}</pre>
{% endfor %}
```

页面会显示这条内容的所有字段和值。常用调试对象：

```jinja
<pre>{{ r|json_safe }}</pre>      {# 循环里的卡片 #}
<pre>{{ item|json_safe }}</pre>   {# 详情页当前内容 #}
<pre>{{ site|json_safe }}</pre>   {# 站点配置 #}
```

> 调试完记得删掉。`json_safe` 已转义不会炸页面，但会把数据全量吐给访客。

## 相关阅读

- [全量速查](/cenkor-admin/template/methods) — 一页查全所有标签
- [结构标签](/cenkor-admin/template/tag) — 分类 / 标签 / 菜单 / 友链
- [站点与配置](/cenkor-admin/template/config) — `page` 对象 / `url` / 分页
