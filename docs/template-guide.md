# 主题模板开发

前台 HTML 由 **Jinja2 主题**渲染，模板存在数据库里，在后台「CMS → 模板工作台」直接改、实时预览、一键回滚。
内置主题由 12 个文件组成；你自己建主题时只覆盖想改的那几个即可，其余自动继承。
整个主题可以导出成 zip 搬到别的站点。

> **这是用户手册，不是框架文档。** 你只需要会 HTML + 一点 Jinja 语法。
> 数据从哪来、能调什么、哪里会报错，下面全部写清。

---

## 一、模板与页面的对应关系

| 访问路径 | 用哪个模板 | 说明 |
|---|---|---|
| `/article/{slug}.html` | `detail.html` | 文章详情 |
| `/product/{slug}.html` | `detail.html` | 产品详情 |
| `/case/{slug}.html` | `detail.html` | 案例详情 |
| `/news/{slug}.html` | `detail.html` | 新闻详情 |
| `/article/`、`/article/?page=2` | `list.html` | 文章列表（分页 12 条/页） |
| `/product/` | `list.html` | 产品列表 |
| `/case/` | `list.html` | 案例列表 |
| `/news/` | `list.html` | 新闻列表 |
| `/category/{slug}/` | `list.html` | 分类列表 |
| `/tag/{slug}/` | `list.html` | 标签列表 |
| `/search/?kw=xxx` | `list.html` | 搜索结果 |
| 任何不存在的页面 | `404.html` | 返回 404 状态码 |

`page.html`（单页类型）目前没有对外路由，写了也不生效。

> `/news`（无斜杠）和 `/news/{slug}`（无 `.html`）是既有的 **JSON 接口**，给前端和
> AI 助手读数据；`/news/` 和 `/news/{slug}.html` 才是给人看的页面。同一段 URL 模式
> 由后端按后缀分流，两种都保留。

`layout.html`、`partials/*`、`macros/*`、`assets/style.css` 是所有页面的组成部分，改它们立刻生效。

### 列表页和详情页的差别

`list.html` 里 `item` 是 `None`、`items` 有数据、`page.pagination` 是真实分页对象；
`detail.html` 里反过来。同一个 `page` 对象，字段完全同构，只是 `page.kind` 不同
（`list` vs `article`/`product`/……）。所以你可以让两个模板共用一套 header 和卡片。

### 部署前提：nginx 必须把这些路径转给后端

官网是纯静态站，nginx 有 `try_files ... /index.html` 兜底。**少一条代理规则，
对应页面就会静默返回官网首页（状态码还是 200）**，看起来像「点了没反应」，极难排查。

需要代理的路径（配置在宝塔 `/www/server/panel/vhost/nginx/<域名>.conf`，不在仓库内）：

| 路径 | 目标 |
|---|---|
| 详情页 `/article/{slug}.html`、`/product/{slug}.html`、`/case/`、`/news/` | `/api/v1/public/$1/$2.html`（**后缀要保留**，后端靠它区分 HTML 与 JSON） |
| `/article/`、`/product/`、`/case/`、`/news/` | `/api/v1/public/<类型>/` |
| `/category/{slug}/`、`/tag/{slug}/` | `/api/v1/public/category/$1/`、`/api/v1/public/tag/$1/` |
| `/search/` | `/api/v1/public/search/`（注意尾斜杠，`/search` 是 JSON 接口） |
| `/sitemap.xml`、`/llms.txt` | 同名后端路径 |

新环境部署时若发现列表页变成官网首页，先查这个，不是模板问题。

---

## 二、五分钟上手

1. 后台进 **CMS → 模板工作台**（`/cms/templates`）
2. 左侧文件树点 `detail.html`
3. 改一句，比如把标题后面加个点
4. 右边预览区约 0.8 秒后自动刷新（改的是详情页，预览直接按 `detail.html` 渲染真实数据）
5. `⌘S` / `Ctrl+S` 保存，或者点保存按钮
6. 保存会同时清掉模板缓存，线上**立即**生效（缓存 30 秒只是兜底，防的是绕过后台直接改库的情况）

改 `partials/header.html` 这类被 include 的文件时，预览会自动挂到宿主页面（`detail.html`）上渲染，
不用来回切文件就能看到效果。

### 主题是怎么一层层回退的

```
数据库里的 cms_templates（你保存的）
        ↓ 没有这个文件
主题自带的内置文件（如果有）
        ↓ 还没有
default 主题的内置文件
        ↓ 渲染出错
极简兜底页（只有标题和正文）
```

所以你想只覆盖 `detail.html` 一个文件完全没问题，其余自动用 default 的。
删掉某个文件（工作台里「还原」）就是让它回退到内置版本。

---

## 三、文件约定

### 目录结构

```
layout.html              布局骨架：<head>、header、<main>、footer，子模板 extends 它
detail.html              详情页（article / product / news / case 共用）
page.html                单页
list.html                列表页（当前未启用）
404.html                 未找到（当前未启用）
partials/meta.html       OG / Twitter / JSON-LD 元信息
partials/header.html     站头 + 主菜单
partials/footer.html     页脚
partials/card.html       列表卡片（约定循环变量叫 r）
partials/pagination.html 分页条
macros/ui.html           宏：button()、tag_list()
assets/style.css         全站样式，会被内联进 <style>
```

### 路径规则（保存和导入时都会校验，不合格直接拒）

| 规则 | 说明 |
|---|---|
| 扩展名白名单 | `.html` `.xml` `.txt` `.json` `.css` `.js` |
| 字符 | 只允许 `字母 数字 _ - . /` |
| 禁止 | 以 `/` 开头、包含 `..`、包含 `\`、包含空字节 |
| 禁止 | **任何路径段以 `_` 开头**，所以 `_macros.html`、`_partials/x.html` 都不行 |
| 长度 | 整个路径不超过 255 字符 |

主题名同样有约束：`^[a-z0-9][a-z0-9_-]{0,63}$` —— 小写字母数字开头，之后可以用连字符和下划线，2–64 位。
中文名、大写、空格都不行（它要当 URL 片段和数据库标识用）。

---

## 四、模板里能拿到什么

详情页渲染时会注入下面这些变量，都是**顶层变量**，不用声明。

| 变量 | 类型 | 说明 |
|---|---|---|
| `page` | dict | 页面元信息，见下表 |
| `item` | dict 或 null | 当前这条内容，见下表。列表页为 `None` |
| `items` | list | 当前页的卡片数组。详情页是 `[]`，列表页有数据 |
| `pagination` | dict | 分页对象。详情页是「空分页」（`total=0`） |
| `base_url` | str | 站点根地址，如 `https://www.cenkor.cn`，没有尾部斜杠 |
| `theme_css` | str | `assets/style.css` 的内容，用 `{{ theme_css\|safe }}` 输出 |
| `theme_name` | str | 当前主题名 |
| `now` | datetime | 渲染时刻 |
| `site` | dict | 站点信息，见「数据 API」 |
| 其余 16 个 | function | 数据 API，见下一节 |

### `page` 对象

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
| `page.og.site_name` | 站点名 |
| `page.og.title` | 标题 |
| `page.og.description` | 描述 |
| `page.og.url` | 规范链接 |
| `page.og.image` | 封面绝对地址，可能为空串 |
| `page.og.video` | 正文里第一个 `<video>` 的地址，没有为空串 |
| `page.json_ld` | 已序列化的 JSON-LD 字符串，用 `{{ page.json_ld\|safe }}` 放进 `<script type="application/ld+json">` |
| `page.published_at` | ISO 时间字符串，可能为 `None` |
| `page.published_text` | `YYYY-MM-DD`，可能为空串 |
| `page.updated_at` | ISO 时间字符串，可能为 `None` |
| `page.ai_origin` | AI 生成溯源，人工写的为 `None` |
| `page.item` | 同顶层 `item` |
| `page.items` | 同顶层 `items`（注意 `page.items` 撞 dict 方法，见第七节，用顶层 `items`） |
| `page.pagination` | 列表页是真实分页对象，详情页为 `None` |

### `item` 对象（详情页）

| 字段 | 说明 |
|---|---|
| `item.id` / `item.slug` / `item.title` | 基本信息 |
| `item.body_html` | **正文 HTML，必须 `\|safe`**，否则会被转义成一堆 `&lt;p&gt;` |
| `item.excerpt` | 摘要（纯文本） |
| `item.cover` | 封面**绝对地址**，可能为空串 |
| `item.seo` | 原始 SEO 字典：`seo.title` / `seo.description` / `seo.og_image` |
| `item.content` | 原始内容字典，字段随内容类型而不同：`content.text` / `content.cover_image` / `content.tagline` … |
| `item.custom_fields` | 自定义字段字典 |
| `item.category` | `{id, slug, name, url}` 或 `None` |
| `item.tags` | 标签**名称**数组，如 `["智能制造", "案例"]`（不是对象） |
| `item.published_at` / `item.updated_at` | datetime 或 `None`，配合 `\|date` 过滤 |
| `item.view_count` | 阅读数 |
| `item.ai_generated` | bool |

`article` 之外的 `kind`（product / news / case）字段是各自表结构的投影，
`item.content` 里放的是该类型专有字段，例如产品有 `content.tagline` / `content.features`，
案例有 `content.industry` / `content.desc`。

> **注意**：`item` 里**没有** `status`、`site_id` 这类内部字段以外的敏感数据，也没有 ORM 对象 —— 全是普通 dict。

---

## 五、数据 API（16 个）

只能用这 16 个函数取数据。它们是**只读**的，绑定当前站点，查不到别的站点。

所有 `limit` 都有上限，超了会被夹到上限值，不会报错。

### 1. `content_list(...)` — 条目列表

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
| `sort` | `'-published_at'` | 前缀 `-` 表示倒序；可选 `published_at` `updated_at` `created_at` `sort` `view_count` `id` |
| `exclude` | `None` | 排除某条 id（做「相关推荐」用） |

返回卡片数组，字段：`id` `type` `slug` `title` `excerpt` `cover` `url` `published_at`
`updated_at` `view_count` `sort` `ai_generated` `content` `custom_fields` `seo` `category` `tags`。

> `product` 读的是产品目录表，卡片字段不同（`is_flagship` `github_url` `demo_url` 等）；
> `article` / `news` / `case` 读的是同一套内容引擎，卡片**完全同构**，可以共用一套卡片模板。
> 卡片里的 `type` 是条目自己的类型，`url` 也是按它拼的 —— `/news/` 列表里的卡片
> 不会错误地指向 `/article/`。

### 2. `content(type, slug)` — 单条详情

```jinja
{% set it = content('article', 'my-post') %}
{% if it %}<h2>{{ it.title }}</h2>{{ it.body_html|safe }}{% endif %}
```

返回和 `content_list` 卡片同构，**额外带 `body_html`**。查不到返回 `None`。

### 3. `related(item, limit=4)` — 相关推荐

同分类优先，不够时用同类型最新补齐，已排除自己。`limit` 上限 12。

```jinja
{% for r in related(item, 3) %}{% include "partials/card.html" %}{% endfor %}
```

### 4. `search(kw, limit=20, page=1)` — 站内搜索

```jinja
{% set res = search(request_kw) %}
<p>共 {{ res.total }} 条</p>
{% for r in res.items %}{% include "partials/card.html" %}{% endfor %}
```

返回 `{items, total, page, per_page, total_pages, kw}`。`limit` 上限 50。
`kw` 为空时返回空结果（不报错）。当前匹配标题和 slug。

### 5. `categories(type='article')` — 分类列表

返回 `[{id, slug, name, icon, color, parent_id, count, url}]`，按 `sort`、`id` 升序。
`count` 是该分类下已发布条目数。

### 6. `category_tree(type='article')` — 分类树

同上，但每个节点多一个 `children` 数组，只返回顶层节点。

```jinja
{% for cat in category_tree() %}
  <a href="{{ cat.url }}">{{ cat.name }}（{{ cat.count }}）</a>
  {% for sub in cat.children %}<a href="{{ sub.url }}">{{ sub.name }}</a>{% endfor %}
{% endfor %}
```

### 7. `tags(type='article', limit=50)` — 标签列表

返回 `[{id, slug, name, color, url}]`，`limit` 上限 200。

### 8. `nav(key='main')` — 菜单

优先读站点配置 `nav.main`，没配就用顶部分类兜底。
返回 `[{label, url, target, children}]`。

```jinja
{% for m in nav('main') %}
  <a href="{{ m.url }}" target="{{ m.target }}">{{ m.label }}</a>
{% endfor %}
```

### 9. `site` — 站点信息（预注入 dict，不是函数）

```jinja
{{ site.name }}
{{ site['brand.name'] }}
{{ site['brand.description'] }}
{{ site.locale or 'zh-CN' }}
```

内容是：站点基础字段（`id` `key` `name` `kind` `domain` `locale` `site_mode` `geo`）
+ 站点设置（原样平铺，所以会出现 `brand.name` 这种带点的 key）
+ SEO 默认值（前缀成 `seo.xxx`）
+ 站点配置表里的键值
+ `base_url`。

> **带点的 key 必须用方括号**：`site['brand.name']`。
> 写成 `site.brand.name` 会去找 `brand` 这个键，拿不到东西。

### 10. `site_meta(key=None)` — 取单个站点配置

```jinja
{{ site_meta('brand.name') }}
```

不传 `key` 返回整个 dict（和 `site` 一样）。`site` 已经预注入了，一般不用这个。

### 11. `pagination(page=1, total=0, per_page=20, window=5)` — 分页对象

返回：

```
{page, per_page, total, total_pages,
 window: [页码数组], has_prev, has_next, prev_page, next_page,
 range_start, range_end}
```

`window` 是当前显示的几个页码，直接循环渲染即可。`page` 会被夹到 `[1, total_pages]` 之间。

### 12. `asset(path='')` — 静态资源地址

```jinja
<link rel="stylesheet" href="{{ asset('assets/style.css') }}">
```

绝对 URL（`http://` `https://` `//` `data:`）原样返回；相对路径会拼上站点根。
不传参数返回站点根 + `/`。

### 13. `url(kind='home', slug=None, page=None)` — 生成链接

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

传 `page=` 会追加 `?page=N`（`search` 是 `&page=N`）。

### 14. `comments(target, limit=20)` — 评论

**目前恒返回 `[]`**（评论表还没建）。接口先占位，模板可以照着写，以后接上自动有数据。

### 15. `form(key='contact')` — 表单定义

从站点配置 `form.<key>` 读，没有就回到内置联系表单：

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

内置返回：`{key: 'contact', title: '联系我们', action: '/api/v1/public/forms/contact',
fields: [{name:'name',label:'称呼',type:'text',required:true}, ...]}`。

### 16. `media_list(kind=None, limit=20)` — 媒体资产

返回 `[{id, url, name, kind, size}]`，`limit` 上限 100。

### 17. `trans(key, lang=None)` — 多语言文案

从站点配置 `i18n.<lang>.<key>` 取；没有就原样返回 `key`。
不传 `lang` 时读 `i18n.current`，再退到 `zh-CN`。

```jinja
<button>{{ trans('buttons.read_more') }}</button>
```

---

## 六、过滤器

16 个过滤器（19 个名字，其中 `md`、`trans`、`format_price` 是别名）。

| 过滤器 | 用法 | 说明 |
|---|---|---|
| `date` | `{{ item.published_at\|date }}` | 默认 `%Y-%m-%d`，可传格式：`\|date('%Y年%m月%d日')` |
| `date_iso` | `{{ item.published_at\|date_iso }}` | ISO 8601 |
| `timesince` | `{{ item.published_at\|timesince }}` | 「3 天前」「刚刚」，未来时间给「X 后」 |
| `markdown` / `md` | `{{ content.text\|markdown }}` | 渲染 Markdown，返回安全 HTML，**不用再 `\|safe`** |
| `excerpt` | `{{ item.content.text\|excerpt(80) }}` | 去标签 + 压空白 + 截断加省略号，默认 160 |
| `striptags` | `{{ html\|striptags }}` | 去所有标签 |
| `truncate_words` | `{{ text\|truncate_words(30) }}` | 按**空格**分词截断，中文文本别用这个 |
| `reading_time` | `{{ item.body_html\|reading_time }}` | 预估阅读分钟数，约 500 字/分钟，最少 1 |
| `slugify` | `{{ 'Hello 世界'\|slugify }}` | 英文转 slug |
| `currency` / `format_price` | `{{ 1299\|currency }}` | 默认 `¥`，`\|currency('$')` 换符号 |
| `number_format` | `{{ 1234567\|number_format }}` | 千分位，`\|number_format(2)` 保留两位 |
| `asset_url` | `{{ item.cover\|asset_url }}` | 同 `asset()`，只是过滤器形式；空值返回空串 |
| `thumb` | `{{ img\|thumb('300x200') }}` | 追加 `?resize=300x200`，仅对 CDN/图片服务有效 |
| `t` / `trans` | `{{ 'article'\|t }}` | 内置词典翻译：article/product/news/case/ai/enterprise/manufacturing 共 7 个词 |
| `highlight` | `{{ title\|highlight(kw) }}` | 把关键词包成 `<mark>`，返回安全 HTML |
| `json_safe` | `{{ data\|json_safe }}` | 序列化并转义 `< > &`，塞进 `<script>` 里不会被提前闭合 |

时间过滤器对 `None`、空串、坏格式都返回空串，不会抛错。

---

## 七、沙箱边界：什么不能做

模板在沙箱里跑，**故意**限制得很紧。下面是真实会踩的坑。

### 自动转义是开着的

`autoescape=True`，所以：

```jinja
{{ item.body_html }}          {# ❌ 输出一堆 &lt;p&gt; #}
{{ item.body_html|safe }}     {# ✅ 正确 #}
{{ theme_css|safe }}          {# ✅ 正确 #}
{{ content.text|markdown }}   {# ✅ markdown 过滤器已标记安全 #}
```

### 下划线属性一律拒绝

```jinja
{{ item.__class__ }}          {# ❌ 拒绝 #}
{{ x._private }}              {# ❌ 拒绝 #}
```

### 不能调用任何函数，除了白名单

```jinja
{{ item.content.get('x') }}       {# ❌ dict.get 是方法，调用被拒 #}
{{ item.content['x'] }}           {# ✅ 方括号取值 #}
{{ item.content.x }}              {# ✅ 点号取普通键 #}

{{ ''.join(items) }}              {# ❌ 字符串方法 #}
{{ items.append(1) }}             {# ❌ 不能改数据 #}
```

只有 16 个数据 API、`{% macro %}` 定义的宏、`range` / `dict` / `namespace` 可以调用。

### dict 的方法名当 key 时，点号会失效

Jinja 取属性时先 `getattr` 再 `getitem`。而 `dict.items` / `keys` / `values` / `get` / `copy`
这些是**方法**，会被沙箱判为不可读，然后**不会**再退回 `getitem`。

```jinja
{{ site.items }}        {# ❌ 拿到的是 Undefined（撞上 dict.items 方法） #}
{{ site['items'] }}     {# ✅ 用方括号 #}
```

`page.items` 同理。这也是为什么列表数据额外暴露成顶层 `items` 变量。

### 硬限制

| 限制 | 值 | 超了会怎样 |
|---|---|---|
| 单页渲染超时 | **8 秒**（含所有数据库查询） | 放弃用户主题，回退内置主题 |
| 输出大小 | **2 MB** | 报「页面输出超过 2MB 上限」 |
| `range()` 长度 | **10000** | 报「range 上限 10000」 |
| 字符串/列表乘法 | 结果不超过 2 MB | 报「输出过大」 |

模板里写到死循环、`range(1000000)`、`'x' * 10**9` 都会被挡住，不会把进程拖死。

### 未定义变量是静默的

用的是 `ChainableUndefined`：`{{ a.b.c }}` 一路查不到就输出空串，不报错。
好处是不会因为少一个字段整页 500；坏处是**写错单词不会提示你**。
调不通时先怀疑变量名拼错。

---

## 八、继承与复用

### 布局继承

```jinja
{# detail.html #}
{% extends "layout.html" %}

{% block title %}{{ page.full_title }}{% endblock %}
{% block content %}
  <h1>{{ item.title }}</h1>
{% endblock %}
```

`layout.html` 提供的 block：`title`、`head`、`content`。

### 引入片段

```jinja
{% include "partials/header.html" %}
{% include "partials/card.html" %}     {# 约定循环变量叫 r #}
```

`include` 共享当前上下文，所以 `partials/card.html` 里直接用 `r` 就行：

```jinja
{# partials/card.html #}
<a class="card" href="{{ r.url }}">
  {% if r.cover %}<img src="{{ r.cover|asset_url }}" alt="{{ r.title }}" loading="lazy">{% endif %}
  <h3>{{ r.title }}</h3>
  {% if r.excerpt %}<p>{{ r.excerpt }}</p>{% endif %}
</a>
```

用 `{% for r in content_list('article', 6) %}` 时变量名必须叫 `r`，否则卡片里取不到。
想换名字就复制一份 partial 自己改。

### 宏

```jinja
{% from "macros/ui.html" import button, tag_list %}

{{ button('查看详情', item.url) }}
{{ button('返回', url('home'), kind='ghost') }}
{{ tag_list(item.tags) }}
```

`macros/ui.html` 自带 `button(label, href, kind='primary')` 和 `tag_list(tags)`。

### 列表页的完整骨架

`list.html` 同时服务文章列表、产品列表、分类、标签、搜索五种页面，
靠 `page.title` / `page.description` 区分标题，不用另写五套模板：

```jinja
{% extends "layout.html" %}
{% block content %}
<section class="section">
  <h1 class="section-title">{{ page.title }}</h1>
  {% if page.description %}<p class="section-desc">{{ page.description }}</p>{% endif %}

  {# 搜索框：提交到 /search/ #}
  <form action="{{ url('search') }}" method="get">
    <input type="search" name="kw" placeholder="搜索…">
    <button type="submit">搜索</button>
  </form>

  <div class="cards">
    {% for r in items %}
      {% include "partials/card.html" %}
    {% else %}
      <p class="empty">暂无内容</p>
    {% endfor %}
  </div>

  {% include "partials/pagination.html" %}
</section>
{% endblock %}
```

`partials/pagination.html` 用 `page.pagination`，链接形如 `?page=2`（相对当前路径），
所以同一个片段在 `/article/`、`/category/x/`、`/search/?kw=x` 下都能正确跳转。

---

## 九、别弄丢 SEO 与 GEO

爬虫和 AI 助手读的是你输出的 HTML 源码。改版式时**至少保留**这些东西：

1. `<title>` 用 `page.full_title`
2. `<meta name="description" content="{{ page.description }}">`
3. `<link rel="canonical" href="{{ page.canonical }}">`
4. `{% include "partials/meta.html" %}` —— OG、Twitter Card、`article:published_time` 全在里面
5. 最后一行 `{{ page.json_ld|safe }}` 塞进 `<script type="application/ld+json">`

`page.json_ld` 是结构化的 `Article` / `Product` 数据，删了不影响人看，但会影响
搜索引擎富摘要和 AI 引用的准确度。

`partials/meta.html` 已经把这些都写好了，除非你知道自己在干什么，否则别删它。

---

## 十、主题包导入导出

工作台**顶部工具栏**有「导出 zip」「导入 zip」两个按钮。

**导出**：内容是「内置基线 + 你的覆盖」合并后的**完整文件集**，外加一个 `manifest.json`
（记录主题名、文件清单、导出时间、站点 id）。拿去另一个站点直接导入就能复用。

**导入**的四道闸：

| 闸 | 限制 |
|---|---|
| 包体积 | 5 MB |
| 文件数 | 300 |
| 单文件 | 1 MB |
| 内容 | UTF-8 文本；路径必须在白名单内 |

另外：`.html` / `.xml` 会逐个做 Jinja 语法校验，**只要有一个文件语法错，整包拒绝**，
并返回每个出错文件的行号。`.css` / `.json` / `.txt` 只校验路径，不校验语法。

导入时 `manifest.json`、`__MACOSX`、`.DS_Store`、`Thumbs.db` 会被自动跳过。
目标主题不存在会自动创建。同名文件**覆盖**（当前界面固定覆盖，没有「跳过已存在」开关）。

---

## 十一、调试与排错

### 先看三个地方

1. **工作台的校验结果** —— 停下来 0.45 秒后自动跑，错误行会标红
2. **工作台的预览区** —— 报错会显示在预览面板上，带异常信息
3. **后端日志** —— `www/wwwlogs/python/cenkor/error.log`，回退时会打印
   `用户主题渲染失败，回退内置主题：...`

### 常见现象对照

| 现象 | 原因 | 处理 |
|---|---|---|
| 页面显示的是旧内容 | 缓存 30 秒没到，或你绕过后台直接改了数据库 | 等半分钟；从工作台保存会立刻清缓存 |
| 改了 `page.html` 没反应 | 单页类型没有对外路由 | 见第一节 |
| 列表页卡片空白 | `partials/card.html` 里取的变量名不是 `r` | 循环变量必须叫 `r` |
| 分页条不显示 | `total_pages` 为 1 时按设计隐藏 | 数据少于 12 条时不显示，正常 |
| 正文变成一堆 `&lt;p&gt;` | 忘了 `\|safe` | `{{ item.body_html\|safe }}` |
| 分类 / 标签不显示 | 这条内容没设分类，或模板用了 `item.category.name` 但 `item.category` 是 `None` | 用 `{% if item.category %}` 包起来 |
| `{{ x.y }}` 输出空 | 变量名拼错，或该 key 是 dict 方法名 | 检查拼写；方法名改用 `x['y']` |
| 报「不可调用」 | 调用了非白名单函数 | 见第七节，只有 16 个 API 和宏可调 |
| 报「属性被拒绝」 | 访问了 `_` 开头的属性 | 去掉它 |
| 报「输出超过 2MB」 | 一次输出了巨大表格/循环 | 减少 `limit`，别用 `range(10000)` 拼字符串 |
| 渲染超时 | 模板里查了太多数据 | 一个页面控制在十几次查询内，别在循环里调 `content()` |
| 线上报 500 但预览正常 | 真实数据里有预览示例数据没有的情况 | 用 `{% if %}` 兜住 `None` |

### 性能建议

- 循环里**不要**调 `content()`，那是每次一条 SQL。列表用 `content_list()` 一次取回
- `content_list()` 的 `limit` 别开满 100，首页 6–12 条足够
- 模板 8 秒超时是整个渲染的总时间，不是单条查询

---

## 十二、接口速查（给前端和运维）

全部在 `/api/v1/cms/templates` 下，需要 CMS 站点权限。

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/themes` | 主题列表（内置 + 数据库） |
| `POST` | `/themes` | 新建主题（从某主题整份 fork） |
| `DELETE` | `/themes/{theme}` | 删除主题（内置名 = 还原到内置） |
| `PUT` | `/themes/active` | 切换站点生效主题 |
| `GET` | `/files` | 文件树（标出 db / builtin / inherited） |
| `GET` | `/file` | 读单个文件（含 diff 用的基线内容） |
| `PUT` | `/file` | 保存文件（自动校验语法 + 清缓存） |
| `DELETE` | `/file` | 删除覆盖，回退到内置 |
| `GET` | `/diff` | 与内置基线逐行对比（unified diff） |
| `GET` | `/export` | 导出主题包 zip |
| `POST` | `/import` | 导入主题包 zip |
| `POST` | `/validate` | 只校验语法，返回 `{valid, error:{line,col,message}}` |
| `POST` | `/preview` | 渲染任意模板字符串 + 自定义数据 |
| `POST` | `/preview-page` | 按真实主题上下文渲染（能调全部数据 API） |
| `POST` | `/render` | 旧接口，渲染字符串，出错抛 400 |
| `GET` | `/context-api` | 返回数据 API 清单，给编辑器做自动提示 |

`/preview-page` 的请求体：

```json
{
  "source": "{% extends \"layout.html\" %}...",
  "path": "detail.html",
  "kind": "article",
  "slug": "my-post",
  "site_id": 1,
  "theme": "default",
  "overrides": { "partials/header.html": "<header>...</header>" }
}
```

- `slug` 不传或查不到时用内置示例数据渲染
- `overrides` 是「其它未保存的文件」，让 include 也能看到实时编辑效果
- `path` 是 `partials/*` 或 `macros/*` 时，会自动挂到 `detail.html` 等宿主页面上渲染

---

## 十三、还有一处 Liquid

前台详情页已全部走 Jinja2。仅剩一个兼容端点
`POST /api/v1/public/templates/render` 仍用 Liquid 渲染（供老的 portal-web 调用），
它不走主题、也不读 `cms_templates`。新代码不要用它。

`docs/dev_guide.md` 里那章「Liquid 模板开发」是历史内容，讲的是这个兼容端点。
写主题请以本文为准。
