"""官方主题 · Landing —— 投放落地页 / 产品单页。

跟 blog、corporate 不是一个物种：它的目标是**一个动作**（留资 / 试用 / 下单），
所以刻意做减法：

* 顶栏只留 logo + 一个 CTA，导航默认收起（``show_nav`` 可开）
* 首屏占满一屏，标题字号拉到 52px，副标题只留一句话
* 卡片带 CSS 计数器序号，天然长成「一 / 二 / 三」的步骤条
* 底部粘性 CTA（``show_sticky_cta``），滚动到哪都能点到

全篇零 JS —— 序号、粘性条、渐变都是纯 CSS。这样它在严格 CSP 下也是满分，
不用为互动付任何安全代价。
"""

from __future__ import annotations

__all__ = ["FILES", "MANIFEST_JSON"]

MANIFEST_JSON = """{
  "schema_version": 1,
  "key": "landing",
  "name": "Landing · \u843d\u5730\u9875",
  "version": "1.0.0",
  "description": "\u6295\u653e\u843d\u5730\u9875\u4e3b\u9898\uff1a\u5168\u5c4f Hero\u3001\u6b65\u9aa4\u5f0f\u5361\u7247\u3001\u5e95\u90e8\u7c98\u6027 CTA\u3002\u96f6 JS\uff0c\u4e13\u6ce8\u8f6c\u5316\u4e00\u4e2a\u52a8\u4f5c\u3002",
  "author": { "name": "Cenkor", "url": "https://cenkor.com" },
  "license": "MIT",
  "icon": "\U0001F680",
  "tags": ["landing", "conversion", "no-js", "minimal"],
  "requires": {
    "core_version": ">=0.5.16",
    "asset_kinds": ["css"]
  },
  "settings": [
    { "key": "brand_color", "type": "color", "label": "\u4e3b\u8272", "default": "#7c3aed", "group": "\u914d\u8272" },
    { "key": "hero_bg", "type": "select", "label": "\u9996\u5c4f\u80cc\u666f", "options": ["gradient", "dark", "light"], "default": "gradient", "group": "\u9996\u5c4f" },
    { "key": "hero_title", "type": "text", "label": "\u4e3b\u6807\u9898", "default": "\u4e09\u5929\u4e0a\u7ebf\u4f60\u7684\u4e1a\u52a1\u7cfb\u7edf", "group": "\u9996\u5c4f" },
    { "key": "hero_subtitle", "type": "textarea", "label": "\u526f\u6807\u9898", "default": "\u4e0d\u7528\u62db\u4eba\u3001\u4e0d\u7528\u7b49\u6392\u671f\uff0c\u5f00\u7bb1\u5373\u7528\u3002\u5148\u8bd5\u4e00\u4e2a\u6708\uff0c\u4e0d\u5408\u9002\u968f\u65f6\u505c\u3002", "group": "\u9996\u5c4f" },
    { "key": "cta_text", "type": "text", "label": "\u4e3b CTA \u6587\u5b57", "default": "\u514d\u8d39\u8bd5\u7528", "group": "\u8f6c\u5316" },
    { "key": "cta_url", "type": "text", "label": "\u4e3b CTA \u94fe\u63a5", "default": "/contact/", "group": "\u8f6c\u5316" },
    { "key": "show_sticky_cta", "type": "bool", "label": "\u5e95\u90e8\u7c98\u6027 CTA", "default": true, "help": "\u6eda\u52a8\u5230\u4efb\u4f55\u4f4d\u7f6e\u90fd\u80fd\u70b9\u5230\u8f6c\u5316\u6309\u94ae", "group": "\u8f6c\u5316" },
    { "key": "show_nav", "type": "bool", "label": "\u9876\u680f\u663e\u793a\u5bfc\u822a", "default": false, "help": "\u843d\u5730\u9875\u9ed8\u8ba4\u53ea\u7559 logo \u548c\u4e00\u4e2a\u6309\u94ae\uff0c\u5c11\u4e00\u4e2a\u51fa\u53e3\u5c31\u591a\u4e00\u5206\u8f6c\u5316", "group": "\u5e03\u5c40" },
    { "key": "footer_note", "type": "text", "label": "\u9875\u811a\u5c0f\u5b57", "default": "\u00a9 Cenkor\uff0c\u4fdd\u7559\u6240\u6709\u6743\u5229", "group": "\u9875\u811a" }
  ],
  "changelog": "1.0.0 \u9996\u53d1",
  "files": [
    "layout.html", "list.html",
    "partials/header.html", "partials/footer.html", "partials/card.html",
    "assets/style.css"
  ]
}
"""

LAYOUT = """<!DOCTYPE html>
<html lang="{{ (site.locale or 'zh-CN') }}" data-hero="{{ theme.hero_bg }}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% block title %}{{ page.full_title }}{% endblock %}</title>
<meta name="description" content="{{ page.description }}">
<link rel="canonical" href="{{ page.canonical }}">
{% include "partials/meta.html" %}
{% block head %}{% endblock %}
<style>{{ theme_css|safe }}</style>
<style>:root{--brand:{{ theme.brand_color }}}</style>
</head>
<body>
{% include "partials/header.html" %}
{% block hero %}{% endblock %}
<main class="container">
{% block content %}{% endblock %}
</main>
{% include "partials/footer.html" %}
{% if theme.show_sticky_cta %}
<div class="sticky-cta">
  <span class="sticky-text">{{ theme.hero_subtitle }}</span>
  <a class="btn btn-primary" href="{{ theme.cta_url or '/contact/' }}">{{ theme.cta_text }}</a>
</div>
{% endif %}
</body>
</html>
"""

HEADER = """<header class="site-header">
  <div class="header-inner">
    <a class="brand" href="{{ url('home') }}">{{ (site['brand.name'] or site.name or 'Cenkor') }}</a>
    {% if theme.show_nav %}
    <nav class="nav">
      {% for item in nav('main') %}
      <a href="{{ item.url }}" target="{{ item.target }}">{{ item.label }}</a>
      {% endfor %}
    </nav>
    {% endif %}
    <a class="btn btn-primary header-cta" href="{{ theme.cta_url or '/contact/' }}">{{ theme.cta_text }}</a>
  </div>
</header>
"""

FOOTER = """<footer class="site-footer">
  <div class="footer-inner">
    <p class="muted small">{{ theme.footer_note }}</p>
    <p class="muted small">
      <a href="{{ base_url }}/llms.txt">llms.txt</a>
      · <a href="{{ base_url }}/sitemap.xml">sitemap</a>
      {% if theme.show_nav %}· <a href="{{ url('search') }}">搜索</a>{% endif %}
    </p>
  </div>
</footer>
"""

CARD = """<a class="card" href="{{ r.url }}">
  <div class="card-step"></div>
  <div class="card-body">
    <h3>{{ r.title }}</h3>
    {% if r.excerpt %}<p class="card-desc">{{ r.excerpt }}</p>{% endif %}
    <span class="card-more">了解 →</span>
  </div>
</a>
"""

LIST = """{% extends "layout.html" %}
{% block hero %}
<section class="hero">
  <div class="hero-inner">
    <h1>{{ theme.hero_title }}</h1>
    <p class="hero-sub">{{ theme.hero_subtitle }}</p>
    <div class="hero-actions">
      <a class="btn btn-primary btn-lg" href="{{ theme.cta_url or '/contact/' }}">{{ theme.cta_text }}</a>
      <a class="btn btn-ghost btn-lg" href="{{ url('search') }}">先看看有什么</a>
    </div>
  </div>
</section>
{% endblock %}
{% block content %}
<section class="section">
  {% if page.title and page.kind != 'home' %}<h1 class="section-title">{{ page.title }}</h1>{% endif %}
  {% if page.description %}<p class="section-desc">{{ page.description }}</p>{% endif %}
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
"""

STYLE = """*, *::before, *::after { box-sizing: border-box; }
:root {
  --brand: #7c3aed;
  --fg: #14151a;
  --muted: #6b7280;
  --line: #ececf1;
  --surface: #faf9ff;
  --maxw: 1000px;
}
html { -webkit-text-size-adjust: 100%; scroll-behavior: smooth; }
body {
  margin: 0;
  background: #fff;
  color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  font-size: 16px;
  line-height: 1.7;
  -webkit-font-smoothing: antialiased;
  padding-bottom: 0;
}
a { color: var(--brand); text-decoration: none; }
img { max-width: 100%; height: auto; }
.container { max-width: var(--maxw); margin: 0 auto; padding: 0 24px; }

/* 顶栏：无边框、极轻 */
.site-header { position: sticky; top: 0; z-index: 30; background: rgba(255,255,255,.86); backdrop-filter: blur(12px); }
.header-inner { max-width: var(--maxw); margin: 0 auto; padding: 14px 24px; display: flex; align-items: center; gap: 26px; }
.brand { font-weight: 700; font-size: 17px; color: var(--fg); letter-spacing: -.2px; }
.nav { display: flex; gap: 20px; font-size: 14.5px; }
.nav a { color: var(--muted); }
.nav a:hover { color: var(--fg); }
.header-cta { margin-left: auto; padding: 8px 18px; font-size: 14px; }

/* 按钮 */
.btn { display: inline-block; border-radius: 999px; font-weight: 600; text-align: center; transition: transform .16s ease, box-shadow .16s ease; }
.btn:hover { transform: translateY(-2px); text-decoration: none; }
.btn-primary { background: var(--brand); color: #fff; padding: 11px 26px; font-size: 15px; box-shadow: 0 8px 22px rgba(124,58,237,.26); }
.btn-primary:hover { box-shadow: 0 12px 30px rgba(124,58,237,.34); }
.btn-ghost { border: 1px solid var(--line); color: var(--fg); background: #fff; padding: 11px 26px; font-size: 15px; }
.btn-lg { padding: 15px 36px; font-size: 16.5px; }

/* Hero */
.hero { position: relative; overflow: hidden; }
.hero-inner { max-width: var(--maxw); margin: 0 auto; padding: 108px 24px 116px; text-align: center; }
.hero h1 { font-size: 52px; line-height: 1.16; letter-spacing: -1.6px; margin: 0 auto 22px; max-width: 15em; }
.hero-sub { font-size: 18px; line-height: 1.7; margin: 0 auto 40px; max-width: 32em; opacity: .82; }
.hero-actions { display: flex; gap: 14px; justify-content: center; flex-wrap: wrap; }

html[data-hero="gradient"] .hero { background: radial-gradient(1200px 480px at 50% -10%, rgba(124,58,237,.16), transparent 70%), linear-gradient(180deg, var(--surface), #fff); }
html[data-hero="dark"] .hero { background: linear-gradient(160deg, #17111f, #2b1b45 55%, #3d2363); color: #fff; }
html[data-hero="dark"] .hero .btn-ghost { background: rgba(255,255,255,.08); border-color: rgba(255,255,255,.24); color: #fff; }
html[data-hero="light"] .hero { background: #fff; }

main.container { padding-top: 72px; padding-bottom: 96px; }
.section-title { font-size: 30px; letter-spacing: -.6px; margin: 0 0 10px; }
.section-desc { color: var(--muted); margin: 0 0 40px; font-size: 16px; }

/* 步骤式卡片：序号靠 CSS 计数器，不用 JS */
.cards { counter-reset: step; display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 22px; }
.card { counter-increment: step; position: relative; display: block; padding: 28px 26px; border: 1px solid var(--line); border-radius: 16px; background: #fff; color: inherit; transition: border-color .18s, transform .18s, box-shadow .18s; }
.card:hover { border-color: rgba(124,58,237,.4); transform: translateY(-3px); box-shadow: 0 14px 34px rgba(20,21,26,.07); text-decoration: none; }
.card-step { display: flex; align-items: center; justify-content: center; width: 34px; height: 34px; border-radius: 10px; background: rgba(124,58,237,.1); color: var(--brand); font-weight: 700; font-size: 14px; margin-bottom: 16px; }
.card-step::before { content: counter(step, decimal-leading-zero); }
.card-cover { display: none; }
.card-body h3 { font-size: 18px; line-height: 1.45; margin: 0 0 8px; letter-spacing: -.2px; }
.card-desc { font-size: 14.5px; color: var(--muted); margin: 0 0 14px; }
.card-more { font-size: 14px; font-weight: 600; color: var(--brand); }
.card-meta { font-size: 12.5px; color: var(--muted); }

/* 正文（落地页也会承载 page 类型内容） */
.post-head { margin-bottom: 28px; }
.post-head h1 { font-size: 38px; line-height: 1.28; letter-spacing: -1px; margin: 0 0 12px; }
.post-meta { color: var(--muted); font-size: 14px; }
.post-cover { width: 100%; border-radius: 16px; margin-bottom: 28px; display: block; }
.post-body { font-size: 17px; }
.post-body h2 { font-size: 26px; margin: 44px 0 14px; letter-spacing: -.4px; }
.post-body h3 { font-size: 20px; margin: 32px 0 10px; }
.post-body p { margin: 0 0 18px; }
.post-body img { border-radius: 12px; }
.post-body pre { background: #14151a; color: #e7e7ee; padding: 18px 20px; border-radius: 12px; overflow-x: auto; font-size: 13.5px; }
.post-body code { background: var(--surface); padding: 2px 6px; border-radius: 4px; font-size: .89em; }
.post-body pre code { background: none; padding: 0; color: inherit; }
.post-body blockquote { margin: 24px 0; padding: 4px 0 4px 18px; border-left: 3px solid var(--brand); color: var(--muted); }
.post-body table { width: 100%; border-collapse: collapse; margin: 22px 0; font-size: 14.5px; display: block; overflow-x: auto; }
.post-body th, .post-body td { border: 1px solid var(--line); padding: 9px 12px; text-align: left; }
.post-body th { background: var(--surface); }
.post-body ul, .post-body ol { padding-left: 22px; margin: 0 0 18px; }

/* chips */
.chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 18px; }
.chip { display: inline-block; padding: 3px 11px; border-radius: 999px; background: rgba(124,58,237,.09); color: var(--brand); font-size: 12.5px; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 999px; background: #fff7ed; color: #c2410c; font-size: 12.5px; }

/* 分页 */
.pagination { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 48px; }
.page-btn { display: inline-flex; align-items: center; justify-content: center; min-width: 38px; height: 38px; padding: 0 13px; border: 1px solid var(--line); border-radius: 999px; font-size: 14px; color: var(--fg); }
.page-btn:hover { border-color: var(--brand); color: var(--brand); text-decoration: none; }
.page-btn.current { background: var(--brand); border-color: var(--brand); color: #fff; }
.page-info { margin-left: auto; font-size: 13px; color: var(--muted); }

/* 底部粘性 CTA */
.sticky-cta { position: sticky; bottom: 0; z-index: 25; display: flex; align-items: center; justify-content: space-between; gap: 20px; max-width: var(--maxw); margin: 0 auto 18px; padding: 12px 14px 12px 26px; background: rgba(20,21,26,.94); color: #fff; border-radius: 999px; backdrop-filter: blur(10px); box-shadow: 0 12px 34px rgba(20,21,26,.24); }
.sticky-text { font-size: 14.5px; opacity: .8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sticky-cta .btn-primary { padding: 10px 24px; font-size: 14.5px; flex: 0 0 auto; }

/* 页脚 */
.site-footer { border-top: 1px solid var(--line); padding: 32px 0 40px; }
.footer-inner { max-width: var(--maxw); margin: 0 auto; padding: 0 24px; text-align: center; }
.footer-inner p { margin: 6px 0; font-size: 13px; }
.muted { color: var(--muted); }
.small { font-size: 12.5px; }
.empty { color: var(--muted); padding: 56px 0; text-align: center; }

/* 404 */
.notfound { text-align: center; padding: 100px 0; }
.notfound h1 { font-size: 80px; margin: 0 0 10px; color: var(--line); letter-spacing: 4px; }

@media (max-width: 720px) {
  .hero-inner { padding: 64px 20px 72px; }
  .hero h1 { font-size: 32px; letter-spacing: -.8px; }
  .hero-sub { font-size: 16px; }
  .header-inner { padding: 12px 20px; gap: 12px; }
  .nav { display: none; }
  .container { padding: 0 20px; }
  main.container { padding-top: 52px; padding-bottom: 72px; }
  .sticky-cta { margin: 0 12px 12px; padding: 10px 10px 10px 18px; }
  .sticky-text { display: none; }
  .sticky-cta .btn-primary { width: 100%; }
  .post-head h1 { font-size: 27px; }
  .page-info { width: 100%; margin-left: 0; }
}
"""

FILES: dict[str, str] = {
    "theme.json": MANIFEST_JSON,
    "layout.html": LAYOUT,
    "list.html": LIST,
    "partials/header.html": HEADER,
    "partials/footer.html": FOOTER,
    "partials/card.html": CARD,
    "assets/style.css": STYLE,
}
