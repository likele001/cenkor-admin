# 全量速查

一页查全：数据 API、过滤器、预注入变量、App 注册标签。
签名与代码里的实际实现同源（后台接口 `/api/v1/cms/templates/context-api`，模板工作台「标签」面板吃的也是它）。

## 数据 API（17 条）

`site` 是预注入 dict 不是函数，其余 16 个都是可调用的只读函数，绑定当前站点。
所有 `limit` 超上限会被**夹到上限**，不报错。

### 内容

| 名称 | 签名 | 说明 |
|---|---|---|
| `content_list` | `content_list(type='article', limit=20, offset=0, category=None, tag=None, sort='-published_at', exclude=None)` | 条目列表，limit 上限 100 |
| `content` | `content(type='article', slug='')` | 单条详情（额外带 `body_html`），查不到返回 `None` |
| `related` | `related(item, limit=4)` | 相关推荐，同分类优先，limit 上限 12 |
| `search` | `search(kw='', limit=20, page=1)` | 站内搜索，匹配标题和 slug，limit 上限 50 |

### 结构

| 名称 | 签名 | 说明 |
|---|---|---|
| `categories` | `categories(type='article')` | 分类列表（带文章数） |
| `category_tree` | `category_tree(type='article')` | 分类树，只返回顶层节点 |
| `tags` | `tags(type='article', limit=50)` | 标签列表，limit 上限 200 |
| `nav` | `nav(key='main')` | 菜单树，读站点配置 `nav.main`，没配用顶部分类兜底 |

### 站点

| 名称 | 签名 | 说明 |
|---|---|---|
| `site` | `site.name`、`site['brand.name']` | 站点信息（预注入 dict，不是函数） |
| `site_meta` | `site_meta(key=None)` | 站点配置取值，不传 key 返回整个 dict |
| `pagination` | `pagination(page=1, total=0, per_page=20, window=5, base_path=None)` | 分页对象，列表页直接用预注入的 `pagination` |
| `asset` | `asset(path='')` | 静态资源地址，相对路径拼站点根 |
| `url` | `url(kind='home', slug=None, page=None)` | 按 URL 规则生成链接 |

### 其他

| 名称 | 签名 | 说明 |
|---|---|---|
| `comments` | `comments(target, limit=20)` | 评论（**预留**，评论表还没建，恒返回空数组） |
| `form` | `form(key='contact')` | 表单定义，读站点配置 `form.<key>`，没配回内置联系表单 |
| `media_list` | `media_list(kind=None, limit=20)` | 媒体资产，limit 上限 100 |
| `trans` | `trans(key, lang=None)` | 多语言文案，取不到原样返回 key |

## 过滤器（16 个，19 个名字）

`md`、`trans`、`format_price` 是别名。时间类过滤器对 `None`、空串、坏格式都返回空串，不抛错。

| 过滤器 | 别名 | 参数 | 说明 |
|---|---|---|---|
| `date` | — | 可选格式串，默认 `%Y-%m-%d` | 日期格式化 |
| `date_iso` | — | 无 | 输出 ISO 8601 |
| `timesince` | — | 无 | 「3 天前」，未来时间给「X 后」 |
| `excerpt` | — | 长度，默认 160 | 去标签 + 压空白 + 截断加省略号 |
| `striptags` | — | 无 | 去掉所有 HTML 标签 |
| `truncate_words` | — | 词数 | 按空格分词截断，**中文文本别用** |
| `reading_time` | — | 无 | 预估阅读分钟数，约 500 字/分钟，最少 1 |
| `slugify` | — | 无 | 英文转 slug |
| `number_format` | — | 小数位，默认 0 | 千分位 |
| `asset_url` | — | 无 | 同 `asset()` 的过滤器形式，空值返回空串 |
| `thumb` | — | 尺寸如 `300x200` | 追加 `?resize=`，需 CDN/图片服务支持 |
| `highlight` | — | 关键词 | 关键词包成 `<mark>`，返回安全 HTML |
| `json_safe` | — | 无 | 序列化并转义，可安全塞进 `<script>` |
| `markdown` | `md` | 无 | 渲染 Markdown，已标记安全，**不用再加 `\|safe`** |
| `currency` | `format_price` | 符号，默认 `¥` | 货币格式 |
| `t` | `trans` | 无 | 内置词典翻译，共 7 个词 |

用法速览：

```jinja
{{ item.published_at|date('%Y年%m月%d日') }}
{{ item.published_at|timesince }}
{{ item.content.text|excerpt(80) }}
{{ item.body_html|reading_time }}
{{ content.text|markdown }}
{{ 1299|currency('$') }}
{{ 1234567|number_format(2) }}
{{ title|highlight(kw) }}
{{ data|json_safe }}
```

## 预注入变量（9 个）

| 变量 | 类型 | 说明 |
|---|---|---|
| `page` | dict | 页面元信息：title / canonical / og / json_ld，详见[站点与配置](/cenkor-admin/template/config) |
| `item` | dict 或 null | 当前内容，列表页为 `None`，字段详见[内容标签](/cenkor-admin/template/article) |
| `items` | list | 当前页卡片数组，详情页为 `[]` |
| `pagination` | dict | 分页对象，详情页是空分页 |
| `site` | dict | 站点信息 |
| `base_url` | str | 站点根地址，无尾斜杠 |
| `theme_css` | str | 主题 `assets/style.css` 内容，用 `\|safe` 输出 |
| `theme_name` | str | 当前主题名 |
| `now` | datetime | 渲染时刻 |

## App 注册标签

App 在 `apps/<key>/template_tags.py` 里声明 `FUNCTIONS` / `FILTERS`，启动时自动注册，卸载自动清理。

| 名称 | 类型 | 来源 | 说明 |
|---|---|---|---|
| `links_list` | 函数 | links | 友情链接列表，收藏优先、点击数次之 |
| `link_domain` | 过滤器 | links | 从 URL 取主机名，去掉 `www.` |

```jinja
{% for l in links_list(category='dev', limit=8) %}
  <a href="{{ l.url }}" title="{{ l.description }}">{{ l.title }}</a>
{% endfor %}

<span>{{ 'https://www.cenkor.cn/doc'|link_domain }}</span>
```

写自己的标签看[自定义标签开发](/cenkor-admin/template/develop)。
