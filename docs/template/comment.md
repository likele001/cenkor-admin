# 评论 · 表单 · 媒体 · 多语言

四个「其他」类的 API。

## `comments(target, limit=20)` — 评论（预留）

**目前恒返回空数组**（评论表还没建）。接口先占位，模板可以照着写，
以后接上自动有数据，不用改模板：

```jinja
{% set cs = comments(item, 20) %}
{% for c in cs %}
  <div class="comment">
    <span>{{ c.author }}</span>
    <p>{{ c.content }}</p>
  </div>
{% endfor %}
```

> 返回结构以上线时为准，当前只保证「不报错、返回空列表」。

## `form(key='contact')` — 表单定义

从站点配置 `form.<key>` 读，没配就回内置联系表单。

内置返回：`{key: 'contact', title: '联系我们', action: '/api/v1/public/forms/contact',
fields: [{name: 'name', label: '称呼', type: 'text', required: true}, ...]}`

```jinja
{% set f = form('contact') %}
<form action="{{ f.action }}" method="post">
  {% for fd in f.fields %}
    <label>{{ fd.label }}{% if fd.required %} *{% endif %}</label>
    {% if fd.type == 'textarea' %}
      <textarea name="{{ fd.name }}" {% if fd.required %}required{% endif %}></textarea>
    {% else %}
      <input type="{{ fd.type }}" name="{{ fd.name }}" {% if fd.required %}required{% endif %}>
    {% endif %}
  {% endfor %}
  <button type="submit">提交</button>
</form>
```

自定义表单：后台站点配置里加 `form.<key>`（字段结构同上），模板里 `form('<key>')` 即取。

## `media_list(kind=None, limit=20)` — 媒体资产

返回 `[{id, url, name, kind, size}]`，`limit` 上限 100。`kind` 可选 `image` 等。

```jinja
{% for m in media_list('image', 8) %}
  <img src="{{ m.url }}" alt="{{ m.name }}">
{% endfor %}
```

## `trans(key, lang=None)` — 多语言文案

从站点配置 `i18n.<lang>.<key>` 取；没有就原样返回 `key`。
不传 `lang` 时读 `i18n.current`，再退到 `zh-CN`。

```jinja
<button>{{ trans('buttons.read_more') }}</button>
```

### `|t` 过滤器 — 内置词典

少量固定词的翻译走过滤器更快，内置词典共 7 个词：
`article`、`product`、`news`、`case`、`ai`、`enterprise`、`manufacturing`。

```jinja
<h2>{{ page.kind|t }}</h2>
```

## 相关阅读

- [内容标签](/cenkor-admin/template/article) — `item` / `content_list` 详情
- [站点与配置](/cenkor-admin/template/config) — `site` / `page` / `url`
- [自定义标签开发](/cenkor-admin/template/develop) — 给自己的 App 加标签
