# 结构标签：分类 · 标签 · 菜单 · 友链

给页面搭骨架的数据源。全部只读、绑定当前站点。

## `categories(type='article')` — 分类列表

返回 `[{id, slug, name, icon, color, parent_id, count, url}]`，按 `sort`、`id` 升序。
`count` 是该分类下已发布条目数。

```jinja
<ul class="cat-nav">
  {% for c in categories('article') %}
    <li><a href="{{ c.url }}">{{ c.name }}（{{ c.count }}）</a></li>
  {% endfor %}
</ul>
```

## `category_tree(type='article')` — 分类树

字段同上，每个节点多一个 `children` 数组，只返回顶层节点。

```jinja
{% for cat in category_tree() %}
  <a href="{{ cat.url }}">{{ cat.name }}（{{ cat.count }}）</a>
  {% for sub in cat.children %}
    <a class="sub" href="{{ sub.url }}">{{ sub.name }}</a>
  {% endfor %}
{% endfor %}
```

## `tags(type='article', limit=50)` — 标签列表

返回 `[{id, slug, name, color, url}]`，`limit` 上限 200。

标签云示例（按条目数排大小需要自己另想，当前返回没有 count）：

```jinja
<div class="tag-cloud">
  {% for t in tags('article', limit=30) %}
    <a href="{{ t.url }}" class="tag">{{ t.name }}</a>
  {% endfor %}
</div>
```

详情页里给当前内容挂标签链接（`item.tags` 是名称数组，不是对象）：

```jinja
{% if item and item.tags %}
  <div class="article-tags">
    {% for name in item.tags %}
      <span>{{ name }}</span>
    {% endfor %}
  </div>
{% endif %}
```

## `nav(key='main')` — 菜单

优先读站点配置 `nav.main`，没配就用顶部分类兜底。
返回 `[{label, url, target, children}]`。

```jinja
<nav class="site-nav">
  {% for m in nav('main') %}
    <a href="{{ m.url }}" target="{{ m.target }}">{{ m.label }}</a>
  {% endfor %}
</nav>
```

带下拉的写法：

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

## 友链（links App 注册标签）

这两个标签由 **links 应用**通过 `template_tags.py` 注册，应用停用/卸载后自动消失。
机制见[自定义标签开发](/cenkor-admin/template/develop)。

### `links_list(category=None, limit=10, only_favorite=False)`

友情链接列表，收藏优先、点击数次之。`limit` 上限 50。

| 参数 | 默认 | 说明 |
|---|---|---|
| `category` | `None` | 按分类过滤 |
| `limit` | `10` | 上限 50 |
| `only_favorite` | `False` | 只看收藏 |

返回 `[{id, title, url, description, category, favicon, is_favorite}]`。

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

### `link_domain` — 过滤器

从 URL 取主机名，去掉 `www.`，显示来源域名用：

```jinja
<span>{{ l.url|link_domain }}</span>
```
