"""官方主题 · Blog —— 长文阅读优先。

跟 default 的差别只在**观感与信息密度**，模板结构基本复用：

* 单栏，正文宽 760px，行距 1.85 —— 长文读起来不累
* 列表是「条目式」而不是卡片网格：图片左、文字右，一屏能扫到更多标题
* 标题用衬线字体，正文仍是系统无衬线 —— 中文衬线在低分屏上糊，只给标题用
* 侧栏可选（``show_sidebar``），开了就变成 768 + 280 两栏

因为 default 的 ``list.html`` / ``detail.html`` 已经够用，这里**只覆盖**：
``layout.html`` / ``partials/header.html`` / ``partials/footer.html`` /
``partials/card.html`` / ``assets/style.css``。
少覆盖一个文件，将来 default 修 bug 时就少一处要同步。
"""

from __future__ import annotations

__all__ = ["FILES", "MANIFEST_JSON"]

MANIFEST_JSON = """{
  "schema_version": 1,
  "key": "blog",
  "name": "Blog · 墨读",
  "version": "1.0.0",
  "description": "长文阅读优先的博客主题：单栏宽正文、条目式列表、可选侧栏。适合技术博客、行业观察、专栏。",
  "author": { "name": "Cenkor", "url": "https://cenkor.com" },
  "license": "MIT",
  "icon": "\U0001F4D6",
  "tags": ["blog", "reading", "serif", "sidebar"],
  "requires": {
    "core_version": ">=0.5.16",
    "asset_kinds": ["css"]
  },
  "settings": [
    { "key": "brand_color", "type": "color", "label": "\u4e3b\u8272", "default": "#1f6f5c", "group": "\u914d\u8272" },
    { "key": "paper_color", "type": "color", "label": "\u7eb8\u5f20\u5e95\u8272", "default": "#fbfaf7", "help": "\u504f\u6696\u7684\u5e95\u8272\u66f4\u9002\u5408\u957f\u6587", "group": "\u914d\u8272" },
    { "key": "content_width", "type": "range", "label": "\u6b63\u6587\u5bbd\u5ea6", "default": 760, "minimum": 640, "maximum": 1040, "step": 20, "help": "\u5355\u4f4d px\u3002\u5f00\u4e86\u4fa7\u680f\u540e\u4e3b\u680f\u4f1a\u81ea\u52a8\u6536\u7a84", "group": "\u5e03\u5c40" },
    { "key": "font_scale", "type": "select", "label": "\u6b63\u6587\u5b57\u53f7", "options": ["compact", "normal", "large"], "default": "large", "group": "\u6392\u7248" },
    { "key": "show_sidebar", "type": "bool", "label": "\u663e\u793a\u4fa7\u680f", "default": false, "help": "\u5f00\u542f\u540e\u53f3\u4fa7\u51fa\u73b0\u7b80\u4ecb / \u5206\u7c7b / \u6807\u7b7e", "group": "\u5e03\u5c40" },
    { "key": "show_date", "type": "bool", "label": "\u5217\u8868\u91cc\u663e\u793a\u65e5\u671f", "default": true, "group": "\u5217\u8868" },
    { "key": "footer_text", "type": "text", "label": "\u9875\u811a\u526f\u6807", "default": "\u575a\u6301\u5199\u6709\u7528\u7684\u4e1c\u897f", "group": "\u9875\u811a" }
  ],
  "changelog": "1.0.0 \u9996\u53d1",
  "files": [
    "layout.html",
    "partials/header.html",
    "partials/footer.html",
    "partials/card.html",
    "assets/style.css"
  ]
}
"""

LAYOUT = """<!DOCTYPE html>
<html lang="{{ (site.locale or 'zh-CN') }}" data-font="{{ theme.font_scale }}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% block title %}{{ page.full_title }}{% endblock %}</title>
<meta name="description" content="{{ page.description }}">
<link rel="canonical" href="{{ page.canonical }}">
{% include "partials/meta.html" %}
{% if page.pagination and page.pagination.prev_url %}<link rel="prev" href="{{ page.pagination.prev_url }}">
{% endif %}{% if page.pagination and page.pagination.next_url %}<link rel="next" href="{{ page.pagination.next_url }}">
{% endif %}{% block head %}{% endblock %}
<style>{{ theme_css|safe }}</style>
<style>:root{--brand:{{ theme.brand_color }};--paper:{{ theme.paper_color }};--maxw:{{ theme.content_width }}px}</style>
</head>
<body>
{% include "partials/header.html" %}
<main class="container{% if theme.show_sidebar %} has-sidebar{% endif %}">
  <div class="col-main">{% block content %}{% endblock %}</div>
  {% if theme.show_sidebar %}
  <aside class="col-side">
    <section class="side-block">
      <h3>{{ (site['brand.name'] or site.name or '关于本站') }}</h3>
      <p class="muted">{{ (site['brand.description'] or '在设置里填一句站点简介，这里就会显示。') }}</p>
    </section>
    <section class="side-block">
      <h3>分类</h3>
      <ul class="side-list">
        {% for c in categories() %}<li><a href="{{ c.url }}">{{ c.name }}</a></li>
        {% else %}<li class="muted">暂无分类</li>{% endfor %}
      </ul>
    </section>
    <section class="side-block">
      <h3>标签</h3>
      <div class="chips">
        {% for t in tags(limit=20) %}<a class="chip" href="{{ t.url }}">{{ t.name }}</a>
        {% else %}<span class="muted">暂无标签</span>{% endfor %}
      </div>
    </section>
  </aside>
  {% endif %}
</main>
{% include "partials/footer.html" %}
</body>
</html>
"""

HEADER = """<header class="site-header">
  <div class="header-inner">
    <a class="brand" href="{{ url('home') }}">
      <span class="brand-mark"></span>{{ (site['brand.name'] or site.name or 'Cenkor') }}
    </a>
    <nav class="nav">
      {% for item in nav('main') %}
      <a href="{{ item.url }}" target="{{ item.target }}">{{ item.label }}</a>
      {% endfor %}
      <a href="{{ url('search') }}">搜索</a>
    </nav>
  </div>
</header>
"""

FOOTER = """<footer class="site-footer">
  <div class="footer-inner">
    <p class="footer-brand">{{ (site['brand.name'] or site.name or 'Cenkor') }}</p>
    <p class="muted">{{ theme.footer_text }}</p>
    <p class="muted small">
      <a href="{{ url('home') }}">首页</a>
      · <a href="{{ base_url }}/llms.txt">llms.txt</a>
      · <a href="{{ base_url }}/sitemap.xml">sitemap</a>
    </p>
  </div>
</footer>
"""

CARD = """<a class="card" href="{{ r.url }}">
  {% if r.cover %}<img class="card-cover" src="{{ r.cover|asset_url }}" alt="{{ r.title }}" loading="lazy">{% endif %}
  <div class="card-body">
    <h3>{{ r.title }}</h3>
    {% if r.excerpt %}<p class="card-desc">{{ r.excerpt }}</p>{% endif %}
    <div class="card-meta">
      {% if r.category %}<span class="chip-plain">{{ r.category.name }}</span>{% endif %}
      {% if theme.show_date and r.published_at %}
      <time datetime="{{ r.published_at }}">{{ r.published_at|date }}</time>
      {% endif %}
    </div>
  </div>
</a>
"""

STYLE = """*, *::before, *::after { box-sizing: border-box; }
:root {
  --brand: #1f6f5c;
  --paper: #fbfaf7;
  --fg: #23201c;
  --muted: #7b7469;
  --line: #e6e1d8;
  --maxw: 760px;
  --serif: "Songti SC", "Noto Serif SC", "Source Han Serif SC", Georgia, "Times New Roman", serif;
}
html { -webkit-text-size-adjust: 100%; }
html[data-font="compact"] { font-size: 15px; }
html[data-font="normal"] { font-size: 16px; }
html[data-font="large"] { font-size: 17.5px; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  line-height: 1.85;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--brand); text-decoration: none; }
a:hover { text-decoration: underline; }
img { max-width: 100%; height: auto; }

.container { max-width: var(--maxw); margin: 0 auto; padding: 0 22px; }
.container.has-sidebar { max-width: calc(var(--maxw) + 300px); display: grid; grid-template-columns: minmax(0, 1fr) 260px; gap: 52px; }
.col-main { min-width: 0; }
.col-side { padding-top: 44px; }

/* header —— 无边框，靠留白分隔 */
.site-header { padding: 26px 0 6px; }
.header-inner { max-width: var(--maxw); margin: 0 auto; padding: 0 22px; display: flex; align-items: center; justify-content: space-between; gap: 18px; flex-wrap: wrap; }
.brand { display: inline-flex; align-items: center; gap: 9px; font-family: var(--serif); font-weight: 700; font-size: 19px; color: var(--fg); letter-spacing: .3px; }
.brand-mark { width: 9px; height: 9px; border-radius: 2px; background: var(--brand); display: inline-block; }
.nav { display: flex; gap: 20px; flex-wrap: wrap; font-size: 14px; }
.nav a { color: var(--muted); }
.nav a:hover { color: var(--brand); text-decoration: none; }

main.container { padding-top: 40px; padding-bottom: 64px; }

/* 正文 */
.post-head { margin-bottom: 30px; }
.post-head h1 { font-family: var(--serif); font-weight: 700; font-size: 33px; line-height: 1.4; letter-spacing: -.2px; margin: 0 0 14px; }
.post-meta { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; color: var(--muted); font-size: 13.5px; }
.post-cover { width: 100%; border-radius: 4px; margin-bottom: 28px; display: block; }
.post-body { font-size: 1em; }
.post-body h2 { font-family: var(--serif); font-size: 23px; margin: 44px 0 14px; }
.post-body h3 { font-family: var(--serif); font-size: 19px; margin: 32px 0 10px; }
.post-body p { margin: 0 0 20px; }
.post-body img { border-radius: 4px; margin: 10px 0; }
.post-body pre { background: #f2efe8; padding: 16px 18px; border-radius: 6px; overflow-x: auto; font-size: 13.5px; line-height: 1.65; }
.post-body code { background: #f2efe8; padding: 2px 6px; border-radius: 3px; font-size: .89em; }
.post-body pre code { background: none; padding: 0; }
.post-body blockquote { margin: 24px 0; padding: 2px 0 2px 20px; border-left: 2px solid var(--brand); color: var(--muted); font-style: italic; }
.post-body table { width: 100%; border-collapse: collapse; margin: 22px 0; font-size: 14.5px; display: block; overflow-x: auto; }
.post-body th, .post-body td { border-bottom: 1px solid var(--line); padding: 9px 12px; text-align: left; }
.post-body th { background: #f6f2ea; font-weight: 600; }
.post-body ul, .post-body ol { padding-left: 24px; margin: 0 0 20px; }
.post-body li { margin: 8px 0; }

/* chips */
.chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 18px; }
.chip { display: inline-block; padding: 2px 10px; border-radius: 3px; background: #eef4f0; color: var(--brand); font-size: 12.5px; }
.chip-plain { color: var(--muted); font-size: 12.5px; }
.badge { display: inline-block; padding: 2px 9px; border-radius: 3px; background: #f7f0e4; color: #96702f; font-size: 12.5px; }

/* 列表：条目式，不是卡片网格 */
.section { }
.section-title { font-family: var(--serif); font-size: 24px; margin: 0 0 6px; }
.section-desc { color: var(--muted); margin: 0 0 26px; font-size: 15px; }
.cards { display: block; border-top: 1px solid var(--line); }
.card { display: flex; gap: 18px; align-items: flex-start; padding: 22px 0; border-bottom: 1px solid var(--line); color: inherit; background: none; }
.card:hover { text-decoration: none; }
.card:hover h3 { color: var(--brand); }
.card-cover { width: 132px; aspect-ratio: 4 / 3; object-fit: cover; border-radius: 4px; flex: 0 0 auto; background: #efece4; }
.card-body { min-width: 0; }
.card-body h3 { font-family: var(--serif); font-size: 19px; line-height: 1.5; margin: 0 0 8px; transition: color .15s; }
.card-desc { font-size: 14.5px; color: var(--muted); margin: 0 0 10px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card-meta { display: flex; align-items: center; gap: 10px; font-size: 12.5px; color: var(--muted); }

/* 分页 */
.pagination { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 34px; font-size: 14px; }
.page-btn { display: inline-flex; align-items: center; justify-content: center; min-width: 34px; height: 34px; padding: 0 10px; border-radius: 4px; color: var(--muted); }
.page-btn:hover { background: #eeeae1; color: var(--fg); text-decoration: none; }
.page-btn.current { background: var(--brand); color: #fff; }
.page-info { margin-left: auto; font-size: 13px; color: var(--muted); }

/* 按钮 */
.btn { display: inline-block; padding: 10px 22px; border-radius: 4px; font-size: 15px; }
.btn-primary { background: var(--brand); color: #fff; }
.btn-primary:hover { filter: brightness(1.08); text-decoration: none; }
.btn-ghost { border: 1px solid var(--line); color: var(--fg); }

/* 侧栏 */
.side-block { margin-bottom: 34px; }
.side-block h3 { font-family: var(--serif); font-size: 15px; letter-spacing: 1px; color: var(--muted); margin: 0 0 12px; font-weight: 600; }
.side-block p { font-size: 14px; margin: 0; }
.side-list { list-style: none; padding: 0; margin: 0; font-size: 14px; }
.side-list li { padding: 6px 0; border-bottom: 1px dashed var(--line); }
.side-list a { color: var(--fg); }
.side-list a:hover { color: var(--brand); }

/* 页脚 */
.site-footer { border-top: 1px solid var(--line); padding: 34px 0 44px; margin-top: 56px; }
.footer-inner { max-width: var(--maxw); margin: 0 auto; padding: 0 22px; text-align: center; }
.footer-inner p { margin: 6px 0; font-size: 13.5px; }
.footer-brand { font-family: var(--serif); font-weight: 700; font-size: 15px; }
.muted { color: var(--muted); }
.small { font-size: 12.5px; }
.empty { color: var(--muted); padding: 48px 0; text-align: center; }

/* 404 */
.notfound { text-align: center; padding: 90px 0; }
.notfound h1 { font-family: var(--serif); font-size: 68px; margin: 0 0 10px; color: var(--line); letter-spacing: 3px; }

@media (max-width: 860px) {
  .container.has-sidebar { display: block; max-width: var(--maxw); }
  .col-side { padding-top: 0; margin-top: 48px; border-top: 1px solid var(--line); padding-top: 32px; }
}
@media (max-width: 640px) {
  .post-head h1 { font-size: 25px; }
  .card-cover { width: 96px; }
  .card-body h3 { font-size: 17px; }
  .card-desc { -webkit-line-clamp: 2; }
  .cards { }
  .container { padding: 0 18px; }
  .header-inner { padding: 0 18px; }
}
"""

FILES: dict[str, str] = {
    "theme.json": MANIFEST_JSON,
    "layout.html": LAYOUT,
    "partials/header.html": HEADER,
    "partials/footer.html": FOOTER,
    "partials/card.html": CARD,
    "assets/style.css": STYLE,
}
