"""内置主题（随代码发布，不依赖数据库）

用户没建主题、或模板渲染失败回退时用这套。
主题在数据库里是可以被覆盖的同名文件：DB 有就用 DB 的，没有就用这里的。
"""
from __future__ import annotations

from typing import Any

__all__ = ["BUILTIN_THEMES", "DEFAULT_THEME", "get_builtin_meta", "get_builtin_source", "list_builtin_themes"]

DEFAULT_THEME = "default"

# ---------------------------------------------------------------- 通用布局

LAYOUT = """<!DOCTYPE html>
<html lang="{{ (site.locale or 'zh-CN') }}">
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
</head>
<body>
{% include "partials/header.html" %}
<main class="container">
{% block content %}{% endblock %}
</main>
{% include "partials/footer.html" %}
</body>
</html>
"""

META_PARTIAL = """<meta property="og:type" content="{{ page.og.type }}">
<meta property="og:site_name" content="{{ page.og.site_name }}">
<meta property="og:title" content="{{ page.og.title }}">
<meta property="og:description" content="{{ page.og.description }}">
<meta property="og:url" content="{{ page.og.url }}">
{% if page.og.image %}<meta property="og:image" content="{{ page.og.image }}">
<meta name="twitter:image" content="{{ page.og.image }}">
{% endif %}{% if page.og.video %}<meta property="og:video" content="{{ page.og.video }}">
<meta property="og:video:type" content="video/mp4">
<meta property="og:video:width" content="1280">
<meta property="og:video:height" content="720">
{% endif %}<meta name="twitter:card" content="{% if page.og.image %}summary_large_image{% else %}summary{% endif %}">
{% if page.published_at %}<meta property="article:published_time" content="{{ page.published_at }}">
{% endif %}{% if page.updated_at %}<meta property="article:modified_time" content="{{ page.updated_at }}">
{% endif %}{% if page.json_ld %}<script type="application/ld+json">{{ page.json_ld|safe }}</script>
{% endif %}"""

HEADER_PARTIAL = """<header class="site-header">
  <div class="container header-inner">
    <a class="brand" href="{{ url('home') }}">{{ (site['brand.name'] or site.name or 'Cenkor') }}</a>
    <nav class="nav">
      {% for item in nav('main') %}
      <a href="{{ item.url }}" target="{{ item.target }}">{{ item.label }}</a>
      {% endfor %}
      <a href="{{ url('search') }}">搜索</a>
    </nav>
  </div>
</header>
"""

FOOTER_PARTIAL = """<footer class="site-footer">
  <div class="container footer-inner">
    <p>{{ (site['brand.name'] or site.name or 'Cenkor') }}{% if site['brand.description'] %} · {{ site['brand.description'] }}{% endif %}</p>
    <p class="muted">
      <a href="{{ url('home') }}">首页</a>
      · <a href="{{ base_url }}/llms.txt">llms.txt</a>
      · <a href="{{ base_url }}/sitemap.xml">sitemap</a>
    </p>
    <p class="muted small">内容可被 AI 助手检索与引用</p>
  </div>
</footer>
"""

CARD_PARTIAL = """<a class="card" href="{{ r.url }}">
  {% if r.cover %}<img class="card-cover" src="{{ r.cover|asset_url }}" alt="{{ r.title }}" loading="lazy">{% endif %}
  <div class="card-body">
    <h3>{{ r.title }}</h3>
    {% if r.excerpt %}<p class="card-desc">{{ r.excerpt }}</p>{% endif %}
    <div class="card-meta">
      {% if r.category %}<span class="chip">{{ r.category.name }}</span>{% endif %}
      {% if r.published_at %}<time datetime="{{ r.published_at }}">{{ r.published_at|date }}</time>{% endif %}
    </div>
  </div>
</a>
"""

PAGINATION_PARTIAL = """{% set pg = page.pagination %}
{% if pg and pg.total_pages > 1 %}
<nav class="pagination" aria-label="分页">
  {% if pg.has_prev %}<a class="page-btn" href="{{ pg.prev_url or ('?page=' ~ pg.prev_page) }}">上一页</a>{% endif %}
  {% for p in (pg.pages or []) %}
    {% if p.current %}<span class="page-btn current">{{ p.n }}</span>
    {% else %}<a class="page-btn" href="{{ p.url or ('?page=' ~ p.n) }}">{{ p.n }}</a>{% endif %}
  {% endfor %}
  {% if pg.has_next %}<a class="page-btn" href="{{ pg.next_url or ('?page=' ~ pg.next_page) }}">下一页</a>{% endif %}
  <span class="page-info">{{ pg.range_start }}–{{ pg.range_end }} / 共 {{ pg.total }} 条</span>
</nav>
{% endif %}
"""

UI_MACROS = """{% macro button(label, href, kind='primary') -%}
<a class="btn btn-{{ kind }}" href="{{ href }}">{{ label }}</a>
{%- endmacro %}

{% macro tag_list(tags) -%}
{% if tags %}<div class="chips">{% for t in tags %}<span class="chip">{{ t }}</span>{% endfor %}</div>{% endif %}
{%- endmacro %}
"""

DETAIL = """{% extends "layout.html" %}
{% block content %}
<article class="post">
  <header class="post-head">
    <h1>{{ item.title }}</h1>
    <div class="post-meta">
      {% if item.category %}<a class="chip" href="{{ item.category.url }}">{{ item.category.name }}</a>{% endif %}
      {% if item.published_at %}<time datetime="{{ item.published_at }}">{{ item.published_at|date }}</time>{% endif %}
      {% if item.view_count %}<span class="muted">{{ item.view_count }} 次阅读</span>{% endif %}
      {% if item.ai_generated %}<span class="badge">AI 辅助生成 · 已人工审核</span>{% endif %}
    </div>
  </header>
  {% if item.cover %}<img class="post-cover" src="{{ item.cover|asset_url }}" alt="{{ item.title }}">{% endif %}
  <div class="post-body">{{ item.body_html|safe }}</div>
  {% if item.tags %}<div class="chips">{% for t in item.tags %}<span class="chip">{{ t }}</span>{% endfor %}</div>{% endif %}
</article>

{% set rel = related(item, 3) %}
{% if rel %}
<section class="section">
  <h2 class="section-title">相关阅读</h2>
  <div class="cards">
    {% for r in rel %}{% include "partials/card.html" %}{% endfor %}
  </div>
</section>
{% endif %}
{% endblock %}
"""

LIST = """{% extends "layout.html" %}
{% block content %}
<section class="section">
  <h1 class="section-title">{{ page.title }}</h1>
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

PAGE = """{% extends "layout.html" %}
{% block content %}
<article class="post">
  <h1>{{ item.title }}</h1>
  <div class="post-body">{{ item.body_html|safe }}</div>
</article>
{% endblock %}
"""

NOT_FOUND = """<!DOCTYPE html>
<html lang="{{ (site.locale or 'zh-CN') }}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>页面不存在 · {{ page.og.site_name }}</title>
<meta name="robots" content="noindex">
<style>{{ theme_css|safe }}</style>
</head>
<body>
{% include "partials/header.html" %}
<main class="container">
  <div class="notfound">
    <h1>404</h1>
    <p>页面不存在或已下线。</p>
    <p><a class="btn btn-primary" href="{{ url('home') }}">返回首页</a></p>
  </div>
</main>
{% include "partials/footer.html" %}
</body>
</html>
"""

STYLE_CSS = """*, *::before, *::after { box-sizing: border-box; }
:root {
  --bg: #ffffff;
  --fg: #1a1d23;
  --muted: #6b7280;
  --line: #e8eaed;
  --brand: #2563eb;
  --brand-soft: #eff4ff;
  --radius: 12px;
  --maxw: 880px;
}
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  font-size: 16px;
  line-height: 1.75;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--brand); text-decoration: none; }
a:hover { text-decoration: underline; }
img { max-width: 100%; height: auto; }
.container { width: 100%; max-width: var(--maxw); margin: 0 auto; padding: 0 20px; }

/* header */
.site-header { border-bottom: 1px solid var(--line); position: sticky; top: 0; background: rgba(255,255,255,.92); backdrop-filter: blur(8px); z-index: 10; }
.header-inner { display: flex; align-items: center; justify-content: space-between; gap: 16px; min-height: 60px; }
.brand { font-weight: 700; font-size: 17px; color: var(--fg); letter-spacing: .2px; }
.nav { display: flex; gap: 18px; flex-wrap: wrap; font-size: 14px; }
.nav a { color: var(--muted); }
.nav a:hover { color: var(--brand); text-decoration: none; }

main.container { padding-top: 36px; padding-bottom: 56px; }

/* article */
.post-head h1 { font-size: 30px; line-height: 1.35; margin: 0 0 12px; letter-spacing: -.3px; }
.post-meta { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; color: var(--muted); font-size: 14px; margin-bottom: 24px; }
.post-cover { width: 100%; border-radius: var(--radius); margin-bottom: 24px; display: block; }
.post-body { font-size: 16.5px; }
.post-body h2 { font-size: 22px; margin: 36px 0 12px; }
.post-body h3 { font-size: 18px; margin: 28px 0 10px; }
.post-body p { margin: 0 0 18px; }
.post-body img { border-radius: 8px; margin: 8px 0; }
.post-body pre { background: #f6f8fa; padding: 16px; border-radius: 10px; overflow-x: auto; font-size: 13.5px; line-height: 1.6; }
.post-body code { background: #f6f8fa; padding: 2px 6px; border-radius: 4px; font-size: .9em; }
.post-body pre code { background: none; padding: 0; }
.post-body blockquote { margin: 20px 0; padding: 4px 0 4px 16px; border-left: 3px solid var(--brand); color: var(--muted); }
.post-body table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14.5px; display: block; overflow-x: auto; }
.post-body th, .post-body td { border: 1px solid var(--line); padding: 8px 12px; text-align: left; }
.post-body th { background: #fafbfc; font-weight: 600; }
.post-body ul, .post-body ol { padding-left: 22px; margin: 0 0 18px; }
.post-body li { margin: 6px 0; }

/* chips & badge */
.chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 20px; }
.chip { display: inline-block; padding: 3px 10px; border-radius: 999px; background: var(--brand-soft); color: var(--brand); font-size: 12.5px; line-height: 1.6; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 999px; background: #fff7ed; color: #c2410c; font-size: 12.5px; }

/* cards */
.section { margin-top: 8px; }
.section-title { font-size: 22px; margin: 0 0 8px; }
.section-desc { color: var(--muted); margin: 0 0 24px; font-size: 15px; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 18px; }
.card { display: flex; flex-direction: column; border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; color: inherit; background: #fff; transition: transform .16s ease, box-shadow .16s ease; }
.card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(15,23,42,.08); text-decoration: none; }
.card-cover { width: 100%; aspect-ratio: 16 / 9; object-fit: cover; display: block; background: #f3f4f6; }
.card-body { padding: 14px 16px 16px; }
.card-body h3 { font-size: 16px; margin: 0 0 6px; line-height: 1.5; }
.card-desc { font-size: 13.5px; color: var(--muted); margin: 0 0 10px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card-meta { display: flex; align-items: center; gap: 10px; font-size: 12.5px; color: var(--muted); }

/* pagination */
.pagination { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 32px; }
.page-btn { display: inline-flex; align-items: center; justify-content: center; min-width: 36px; height: 36px; padding: 0 12px; border: 1px solid var(--line); border-radius: 8px; font-size: 14px; color: var(--fg); }
.page-btn:hover { border-color: var(--brand); color: var(--brand); text-decoration: none; }
.page-btn.current { background: var(--brand); border-color: var(--brand); color: #fff; }
.page-info { margin-left: auto; font-size: 13px; color: var(--muted); }

/* buttons */
.btn { display: inline-block; padding: 10px 20px; border-radius: 8px; font-size: 15px; }
.btn-primary { background: var(--brand); color: #fff; }
.btn-primary:hover { background: #1d4ed8; text-decoration: none; }
.btn-ghost { border: 1px solid var(--line); color: var(--fg); }

/* footer */
.site-footer { border-top: 1px solid var(--line); padding: 28px 0 36px; margin-top: 40px; }
.footer-inner p { margin: 6px 0; font-size: 13.5px; }
.muted { color: var(--muted); }
.small { font-size: 12.5px; }
.empty { color: var(--muted); padding: 40px 0; text-align: center; }

/* 404 */
.notfound { text-align: center; padding: 80px 0; }
.notfound h1 { font-size: 72px; margin: 0 0 8px; color: var(--muted); letter-spacing: 2px; }

@media (max-width: 640px) {
  body { font-size: 15.5px; }
  .container { padding: 0 16px; }
  .post-head h1 { font-size: 24px; }
  .post-body { font-size: 16px; }
  .cards { grid-template-columns: 1fr; }
  .header-inner { min-height: 54px; }
  .nav { gap: 12px; font-size: 13px; }
  .page-info { width: 100%; margin-left: 0; }
}
"""

_PAGE_FILES: dict[str, str] = {
    "layout.html": LAYOUT,
    "list.html": LIST,
    "detail.html": DETAIL,
    "page.html": PAGE,
    "404.html": NOT_FOUND,
    "partials/meta.html": META_PARTIAL,
    "partials/header.html": HEADER_PARTIAL,
    "partials/footer.html": FOOTER_PARTIAL,
    "partials/card.html": CARD_PARTIAL,
    "partials/pagination.html": PAGINATION_PARTIAL,
    "macros/ui.html": UI_MACROS,
    "assets/style.css": STYLE_CSS,
}

_META: dict[str, dict[str, Any]] = {
    "default": {
        "name": "Default",
        "version": "1.0.0",
        "author": "Cenkor",
        "description": "通用内容主题：文章/新闻/产品详情 + 列表 + 分页",
        "files": list(_PAGE_FILES.keys()),
    },
}

BUILTIN_THEMES: dict[str, dict[str, str]] = {"default": _PAGE_FILES}


def get_builtin_source(theme: str, path: str) -> str | None:
    return BUILTIN_THEMES.get(theme or DEFAULT_THEME, {}).get(path)


def get_builtin_meta(theme: str) -> dict[str, Any] | None:
    return _META.get(theme or DEFAULT_THEME)


def list_builtin_themes() -> list[str]:
    return list(BUILTIN_THEMES.keys())
