# 模板标签总览

主题模板里能用的东西分四类：**预注入变量**、**数据 API**（只读函数）、**过滤器**、**App 注册标签**。
本目录是参考手册，一页一个主题；动手教程看 [主题模板开发](/cenkor-admin/template-guide)。

## 四类东西

| 分类 | 是什么 | 举例 | 详见 |
|---|---|---|---|
| 预注入变量 | 渲染时直接就在，不用取 | `item`、`items`、`page`、`site` | [站点与配置](/cenkor-admin/template/config) |
| 数据 API | 只读函数，绑定当前站点，跨站点查不到 | `content_list()`、`categories()`、`url()` | [内容标签](/cenkor-admin/template/article)、[结构标签](/cenkor-admin/template/tag) |
| 过滤器 | 管道右侧加工数据，可链式 | `\|date`、`\|excerpt`、`\|markdown` | [全量速查](/cenkor-admin/template/methods) |
| App 注册标签 | 各 App 在 `template_tags.py` 里声明，启动自动注册 | `links_list()`、`link_domain` | [自定义标签开发](/cenkor-admin/template/develop) |

## 一个列表页长什么样

```jinja
{% extends "layout.html" %}

{% block main %}
  <h1>{{ page.title }}</h1>
  {% for r in items %}
    <article class="card">
      <a href="{{ r.url }}">{{ r.title }}</a>
      <p>{{ r.excerpt|excerpt(80) }}</p>
      <time>{{ r.published_at|date('%Y年%m月%d日') }}</time>
    </article>
  {% endfor %}

  {% for p in pagination.pages %}
    <a href="{{ p.url }}" {% if p.current %}class="on"{% endif %}>{{ p.n }}</a>
  {% endfor %}
{% endblock %}
```

## 参考页导航

| 页面 | 内容 |
|---|---|
| [全量速查](/cenkor-admin/template/methods) | 17 个数据 API + 16 个过滤器 + 9 个变量，一页查全 |
| [内容标签](/cenkor-admin/template/article) | `content_list` / `content` / `related` / `search`，含 `item` 字段表 |
| [结构标签](/cenkor-admin/template/tag) | 分类、标签、菜单、友链 |
| [站点与配置](/cenkor-admin/template/config) | `site`、`page` 对象、URL 规则、分页、静态资源 |
| [评论·表单·媒体·多语言](/cenkor-admin/template/comment) | `comments` / `form` / `media_list` / `trans` |
| [自定义标签开发](/cenkor-admin/template/develop) | `macro` 复用 + App 注册 `template_tags.py` |

## 版式约定

参考页里每个标签固定按四段说明，翻任何一页结构都一样：

| 段落 | 内容 |
|---|---|
| **语法** | 标准调用写法，一段代码 |
| **参数** | 参数表：名称 / 类型 / 默认值 / 说明 |
| **返回** | 返回结构（代码块展示 dict / list 形态） |
| **示例** | 完整可用的模板片段 |

过滤器没有「参数」时写管道左侧值的类型；预注入变量没有「语法」，直接给返回结构。

## 沙箱边界（背下来）

1. 自动转义开着：输出 HTML 必须加 `|safe`，否则正文变一堆 `&lt;p&gt;`。
2. 不能调用 Python 内置函数，只能调上面的 API 与 `{% macro %}`。
3. 不能访问 `_` 开头的属性（挡住内部字段）。
4. 单页输出上限 2MB，乘法结果同样受限。
5. 模板名只能是主题内相对路径，不能 `..` 穿越。

## 在线速查

不用翻文档也行：**后台 → CMS → 模板工作台 → 「标签」面板**，数据和本目录同源
（都来自 `/api/v1/cms/templates/context-api`），点一下直接插到光标处。
