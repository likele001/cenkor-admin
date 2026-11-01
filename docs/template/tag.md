# 结构标签：分类 · 标签 · 菜单 · 友链

给页面搭骨架的数据源。全部只读、绑定当前站点。
每个标签统一按 **语法 → 参数 → 返回 → 示例** 四段说明。

## `categories(type='article')` — 分类列表

**语法**

```jinja
{% for c in categories('article') %} ... {% endfor %}
```

**参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `type` | str | `'article'` | 内容类型 key |

**返回**

按 `sort`、`id` 升序；`count` 是该分类下已发布条目数。

```text
[
  {
    "id": 1, "slug": "news", "name": "新闻",
    "icon": "", "color": "",
    "parent_id": null, "count": 12,
    "url": "/category/news/"
  }
]
```

**示例**

```jinja
<ul class="cat-nav">
  {% for c in categories('article') %}
    <li><a href="{{ c.url }}">{{ c.name }}（{{ c.count }}）</a></li>
  {% endfor %}
</ul>
```

## `category_tree(type='article')` — 分类树

**语法**

```jinja
{% for cat in category_tree() %} ... {% endfor %}
```

**参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `type` | str | `'article'` | 内容类型 key |

**返回**

字段同 `categories`，每个节点多一个 `children` 数组；只返回顶层节点，子分类在 `children` 里。

```text
[
  {
    "id": 1, "slug": "news", "name": "新闻", "count": 12, "url": "...",
    "children": [
      { "id": 5, "slug": "company", "name": "公司动态", "count": 3, "url": "...", "children": [] }
    ]
  }
]
```

**示例**

```jinja
{% for cat in category_tree() %}
  <a href="{{ cat.url }}">{{ cat.name }}（{{ cat.count }}）</a>
  {% for sub in cat.children %}
    <a class="sub" href="{{ sub.url }}">{{ sub.name }}</a>
  {% endfor %}
{% endfor %}
```

## `tags(type='article', limit=50)` — 标签列表

**语法**

```jinja
{% for t in tags('article', limit=30) %} ... {% endfor %}
```

**参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `type` | str | `'article'` | 内容类型 key |
| `limit` | int | `50` | 上限 200 |

**返回**

```text
[
  { "id": 1, "slug": "mes", "name": "智能制造", "color": "", "url": "/tag/mes/" }
]
```

**示例**

标签云：

```jinja
<div class="tag-cloud">
  {% for t in tags('article', limit=30) %}
    <a href="{{ t.url }}" class="tag">{{ t.name }}</a>
  {% endfor %}
</div>
```

详情页里给当前内容挂标签（`item.tags` 是名称数组，不是对象）：

```jinja
{% if item and item.tags %}
  <div class="article-tags">
    {% for name in item.tags %}<span>{{ name }}</span>{% endfor %}
  </div>
{% endif %}
```

## `nav(key='main')` — 菜单

**语法**

```jinja
{% for m in nav('main') %} ... {% endfor %}
```

**参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `key` | str | `'main'` | 菜单标识，读站点配置 `nav.main`，没配用顶部分类兜底 |

**返回**

```text
[
  {
    "label": "首页",
    "url": "/",
    "target": "_self",
    "children": [ { "label": "...", "url": "...", "target": "...", "children": [] } ]
  }
]
```

**示例**

平铺导航：

```jinja
<nav class="site-nav">
  {% for m in nav('main') %}
    <a href="{{ m.url }}" target="{{ m.target }}">{{ m.label }}</a>
  {% endfor %}
</nav>
```

带下拉：

```jinja
{% for m in nav('main') %}
  <a href="{{ m.url }}">{{ m.label }}</a>
  {% if m.children %}
    <div class="dropdown">
      {% for sub in m.children %}
        <a href="{{ sub.url }}">{{ sub.label }}</a>
      {% endfor %}
    </div>
  {% endif %}
{% endfor %}
```

## `links_list(...)` — 友情链接列表

links 应用注册的标签，应用停用/卸载后自动消失。机制见[自定义标签开发](/cenkor-admin/template/develop)。

**语法**

```jinja
{% for l in links_list(category='dev', limit=8) %} ... {% endfor %}
```

**参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `category` | str | `None` | 按分类过滤 |
| `limit` | int | `10` | 上限 50 |
| `only_favorite` | bool | `False` | 只看收藏 |

**返回**

收藏优先、点击数次之。

```text
[
  {
    "id": 1, "title": "站点名", "url": "https://...",
    "description": "描述", "category": "dev",
    "favicon": "图标地址", "is_favorite": true
  }
]
```

**示例**

```jinja
<aside class="friend-links">
  <h3>友情链接</h3>
  {% for l in links_list(limit=12) %}
    <a href="{{ l.url }}" title="{{ l.description }}" target="_blank" rel="noopener">
      {{ l.title }}
    </a>
  {% endfor %}
</aside>
```

## `link_domain` — 过滤器（URL 取域名）

从 URL 取主机名，去掉 `www.`，显示来源域名用。过滤器，不是函数。

**语法**

```jinja
{{ l.url|link_domain }}
```

**参数**

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| （管道左侧值） | str | — | 任意 URL 字符串 |

**返回**

主机名字符串，如 `cenkor.cn`；解析失败返回空串。

**示例**

```jinja
<span>{{ l.url|link_domain }}</span>
```
