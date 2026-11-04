"""官方主题 · Corporate —— 企业官网 / B2B 门面。

与 default 的差别是**信息架构**，不是配色：

* 深色顶栏 + 高对比 CTA，「联系我们」永远在右手边
* 列表页首页带 Hero（标题 / 副标题 / 主按钮），翻到第 2 页就不再出现
* 卡片带顶部色条，视觉上区分内容类型
* 页脚三列（品牌 / 导航 / 联系方式），带备案号位

这些差异靠 CSS 做不出来，必须动模板，所以覆盖得比 blog 多一个
``list.html`` 和 ``page.html``。
"""

from __future__ import annotations

__all__ = ["FILES", "MANIFEST_JSON"]

MANIFEST_JSON = """{
  "schema_version": 1,
  "key": "corporate",
  "name": "Corporate · \u4f01\u4e1a\u5b98\u7f51",
  "version": "1.1.0",
  "description": "\u4f01\u4e1a\u5b98\u7f51\u4e3b\u9898\uff1a\u6df1\u8272\u9876\u680f\u3001Hero \u533a\u3001\u7279\u8272\u5361\u7247\u3001\u591a\u5217\u9875\u811a\u3002\u9002\u5408 B2B \u5236\u9020\u4e1a\u3001\u65b9\u6848\u5546\u3001\u54a8\u8be2\u670d\u52a1\u5c55\u793a\u3002",
  "author": { "name": "Cenkor", "url": "https://cenkor.com" },
  "license": "MIT",
  "icon": "\U0001F3E2",
  "tags": ["corporate", "b2b", "hero", "landing"],
  "requires": {
    "core_version": ">=0.5.16",
    "asset_kinds": ["css"]
  },
  "settings": [
    { "key": "brand_color", "type": "color", "label": "\u54c1\u724c\u4e3b\u8272", "default": "#0f4c81", "group": "\u914d\u8272" },
    { "key": "accent_color", "type": "color", "label": "\u5f3a\u8c03\u8272", "default": "#f59e0b", "help": "\u7528\u4e8e CTA \u6309\u94ae\u4e0e\u5361\u7247\u9876\u90e8\u8272\u6761", "group": "\u914d\u8272" },
    { "key": "nav_style", "type": "select", "label": "\u9876\u680f\u98ce\u683c", "options": ["dark", "light"], "default": "dark", "group": "\u5e03\u5c40" },
    { "key": "hero_title", "type": "text", "label": "Hero \u6807\u9898", "default": "\u8ba9\u5236\u9020\u73af\u8282\u5c11\u4e00\u70b9\u4eba\u4e3a\u5dee\u9519", "group": "\u9996\u5c4f" },
    { "key": "hero_subtitle", "type": "textarea", "label": "Hero \u526f\u6807\u9898", "default": "\u4ece\u8ba2\u5355\u5230\u4ea4\u4ed8\u5168\u94fe\u8def\u53ef\u89c6\uff0c\u8ba9\u6bcf\u4e00\u9053\u5de5\u5e8f\u90fd\u6709\u636e\u53ef\u67e5\u3002", "group": "\u9996\u5c4f" },
    { "key": "hero_cta_text", "type": "text", "label": "\u4e3b\u6309\u94ae\u6587\u5b57", "default": "\u9884\u7ea6\u6f14\u793a", "group": "\u9996\u5c4f" },
    { "key": "hero_cta_url", "type": "text", "label": "\u4e3b\u6309\u94ae\u94fe\u63a5", "default": "/contact/", "help": "\u586b\u7ad9\u5185\u8def\u5f84\u6216\u5b8c\u6574 URL", "group": "\u9996\u5c4f" },
    { "key": "show_hero", "type": "bool", "label": "\u9996\u9875\u663e\u793a Hero", "default": true, "group": "\u9996\u5c4f" },
    { "key": "contact_phone", "type": "text", "label": "\u8054\u7cfb\u7535\u8bdd", "default": "", "group": "\u9875\u811a" },
    { "key": "icp_no", "type": "text", "label": "\u5907\u6848\u53f7", "default": "", "help": "\u586b\u4e86\u5c31\u5728\u9875\u811a\u663e\u793a", "group": "\u9875\u811a" }
  ],
  "widgets": [
    { "name": "stats", "title": "\u6570\u5b57\u7edf\u8ba1", "height": 150,
      "description": "\u9996\u5c4f\u4e0b\u65b9\u7684\u5173\u952e\u6307\u6807\u6761\uff0c\u6570\u5b57\u4ece 0 \u6eda\u52a8\u5230\u76ee\u6807\u503c\u3002\u8dd1\u5728 iframe \u6c99\u7bb1\u91cc\uff0c\u4e0d\u9700\u8981\u5f00\u540c\u6e90\u811a\u672c" }
  ],
  "changelog": "1.1.0 \u65b0\u589e stats \u6570\u5b57\u7edf\u8ba1\u7ec4\u4ef6\uff08iframe \u6c99\u7bb1\uff0c\u96f6\u540c\u6e90\u811a\u672c\uff09",
  "files": [
    "layout.html", "list.html", "page.html",
    "partials/header.html", "partials/footer.html", "partials/card.html",
    "widgets/stats.html", "widgets/stats.js",
    "assets/style.css"
  ]
}
"""

LAYOUT = """<!DOCTYPE html>
<html lang="{{ (site.locale or 'zh-CN') }}" data-nav="{{ theme.nav_style }}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% block title %}{{ page.full_title }}{% endblock %}</title>
<meta name="description" content="{{ page.description }}">
<link rel="canonical" href="{{ page.canonical }}">
{% include "partials/meta.html" %}
{% block head %}{% endblock %}
<style>{{ theme_css|safe }}</style>
<style>:root{--brand:{{ theme.brand_color }};--accent:{{ theme.accent_color }}}</style>
</head>
<body>
{% include "partials/header.html" %}
{% block hero %}{% endblock %}
<main class="container">
{% block content %}{% endblock %}
</main>
{% include "partials/footer.html" %}
</body>
</html>
"""

HEADER = """<header class="site-header">
  <div class="header-inner">
    <a class="brand" href="{{ url('home') }}">{{ (site['brand.name'] or site.name or 'Cenkor') }}</a>
    <nav class="nav">
      {% for item in nav('main') %}
      <a href="{{ item.url }}" target="{{ item.target }}">{{ item.label }}</a>
      {% endfor %}
    </nav>
    <div class="header-actions">
      <a class="nav-search" href="{{ url('search') }}" aria-label="搜索">搜索</a>
      {% if theme.hero_cta_text %}
      <a class="btn btn-accent" href="{{ theme.hero_cta_url or '/contact/' }}">{{ theme.hero_cta_text }}</a>
      {% endif %}
    </div>
  </div>
</header>
"""

FOOTER = """<footer class="site-footer">
  <div class="footer-inner">
    <div class="footer-col footer-brand-col">
      <p class="footer-brand">{{ (site['brand.name'] or site.name or 'Cenkor') }}</p>
      <p class="muted">{{ (site['brand.description'] or '') }}</p>
    </div>
    <div class="footer-col">
      <h4>快速导航</h4>
      <ul>
        {% for item in nav('main') %}<li><a href="{{ item.url }}">{{ item.label }}</a></li>{% endfor %}
        <li><a href="{{ base_url }}/sitemap.xml">站点地图</a></li>
      </ul>
    </div>
    <div class="footer-col">
      <h4>联系我们</h4>
      <ul>
        {% if theme.contact_phone %}<li class="muted">{{ theme.contact_phone }}</li>{% endif %}
        <li class="muted">{{ site['brand.description'] or '在工作时间联系我们' }}</li>
      </ul>
    </div>
  </div>
  <div class="footer-bottom">
    <span class="muted small">{% if theme.icp_no %}{{ theme.icp_no }} · {% endif %}{{ (site['brand.name'] or site.name or 'Cenkor') }}</span>
    <span class="muted small"><a href="{{ base_url }}/llms.txt">llms.txt</a></span>
  </div>
</footer>
"""

CARD = """<a class="card" href="{{ r.url }}">
  {% if r.cover %}<img class="card-cover" src="{{ r.cover|asset_url }}" alt="{{ r.title }}" loading="lazy">{% endif %}
  <div class="card-body">
    {% if r.category %}<span class="card-tag">{{ r.category.name }}</span>{% endif %}
    <h3>{{ r.title }}</h3>
    {% if r.excerpt %}<p class="card-desc">{{ r.excerpt }}</p>{% endif %}
    <span class="card-more">查看详情 →</span>
  </div>
</a>
"""

LIST = """{% extends "layout.html" %}
{% block hero %}
{% if theme.show_hero and is_home and (not page.pagination or page.pagination.current in (none, 1)) %}
<section class="hero">
  <div class="hero-inner">
    <h1>{{ theme.hero_title }}</h1>
    <p class="hero-sub">{{ theme.hero_subtitle }}</p>
    {% if theme.hero_cta_text %}
    <a class="btn btn-accent btn-lg" href="{{ theme.hero_cta_url or '/contact/' }}">{{ theme.hero_cta_text }}</a>
    {% endif %}
    {{ widget('stats', {
         'accent': theme.accent_color,
         'items': [
           {'value': 1200, 'suffix': '+', 'label': '服务企业'},
           {'value': 36, 'suffix': '%', 'label': '平均降本'},
           {'value': 72, 'suffix': 'h', 'label': '上线耗时'},
           {'value': 99.9, 'suffix': '%', 'label': '交付准时率'}
         ]
       }, height=150) }}
  </div>
</section>
{% endif %}
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

PAGE = """{% extends "layout.html" %}
{% block content %}
<article class="post page-article">
  <header class="post-head">
    <h1>{{ item.title }}</h1>
    {% if item.published_at %}<div class="post-meta"><time datetime="{{ item.published_at }}">{{ item.published_at|date }}</time></div>{% endif %}
  </header>
  {% if item.cover %}<img class="post-cover" src="{{ item.cover|asset_url }}" alt="{{ item.title }}">{% endif %}
  <div class="post-body">{{ item.body_html|safe }}</div>
</article>
{% endblock %}
"""

STYLE = """*, *::before, *::after { box-sizing: border-box; }
:root {
  --brand: #0f4c81;
  --accent: #f59e0b;
  --fg: #101828;
  --muted: #667085;
  --line: #e4e7ec;
  --surface: #f8fafc;
  --radius: 10px;
  --maxw: 1120px;
}
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: #fff;
  color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  font-size: 16px;
  line-height: 1.75;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--brand); text-decoration: none; }
img { max-width: 100%; height: auto; }
.container { max-width: var(--maxw); margin: 0 auto; padding: 0 24px; }

/* 顶栏：默认深色，nav_style=light 时翻成浅色 */
.site-header { background: var(--brand); color: #fff; position: sticky; top: 0; z-index: 20; }
html[data-nav="light"] .site-header { background: #fff; color: var(--fg); border-bottom: 1px solid var(--line); }
.header-inner { max-width: var(--maxw); margin: 0 auto; padding: 0 24px; min-height: 66px; display: flex; align-items: center; gap: 28px; }
.brand { font-weight: 700; font-size: 18px; color: inherit; letter-spacing: .2px; white-space: nowrap; }
.nav { display: flex; gap: 24px; flex-wrap: wrap; font-size: 15px; }
.site-header .nav a { color: rgba(255,255,255,.78); }
.site-header .nav a:hover { color: #fff; }
html[data-nav="light"] .site-header .nav a { color: var(--muted); }
html[data-nav="light"] .site-header .nav a:hover { color: var(--brand); }
.header-actions { margin-left: auto; display: flex; align-items: center; gap: 18px; }
.nav-search { font-size: 14px; color: rgba(255,255,255,.7); }
html[data-nav="light"] .nav-search { color: var(--muted); }

/* 按钮 */
.btn { display: inline-block; padding: 9px 20px; border-radius: 8px; font-size: 14.5px; font-weight: 600; transition: transform .15s, box-shadow .15s; }
.btn:hover { transform: translateY(-1px); text-decoration: none; }
.btn-accent { background: var(--accent); color: #1a1206; box-shadow: 0 4px 14px rgba(245,158,11,.28); }
.btn-primary { background: var(--brand); color: #fff; }
.btn-lg { padding: 13px 32px; font-size: 16px; border-radius: 10px; }
.btn-ghost { border: 1px solid var(--line); color: var(--fg); }

/* Hero */
.hero { background: linear-gradient(160deg, #0b3a63 0%, var(--brand) 55%, #14639e 100%); color: #fff; }
html[data-nav="light"] .hero { background: var(--surface); color: var(--fg); }
.hero-inner { max-width: var(--maxw); margin: 0 auto; padding: 84px 24px 92px; }
.hero h1 { font-size: 44px; line-height: 1.22; letter-spacing: -.8px; margin: 0 0 18px; max-width: 20em; }
.hero-sub { font-size: 18px; line-height: 1.7; margin: 0 0 34px; max-width: 34em; opacity: .9; }

main.container { padding-top: 56px; padding-bottom: 72px; }
.section-title { font-size: 28px; letter-spacing: -.4px; margin: 0 0 8px; }
.section-desc { color: var(--muted); margin: 0 0 32px; font-size: 16px; }

/* 卡片：顶部色条 */
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 24px; }
.card { display: flex; flex-direction: column; border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; background: #fff; color: inherit; border-top: 3px solid var(--accent); transition: box-shadow .18s, transform .18s; }
.card:hover { transform: translateY(-3px); box-shadow: 0 12px 32px rgba(16,24,40,.10); text-decoration: none; }
.card-cover { width: 100%; aspect-ratio: 16 / 9; object-fit: cover; display: block; background: var(--surface); }
.card-body { padding: 20px 22px 24px; display: flex; flex-direction: column; flex: 1; }
.card-tag { display: inline-block; align-self: flex-start; padding: 2px 10px; border-radius: 999px; background: #eef4fb; color: var(--brand); font-size: 12px; margin-bottom: 10px; }
.card-body h3 { font-size: 18px; line-height: 1.5; margin: 0 0 10px; }
.card-desc { font-size: 14.5px; color: var(--muted); margin: 0 0 16px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.card-more { margin-top: auto; font-size: 14px; color: var(--brand); font-weight: 600; }

/* 正文 */
.post-head { margin-bottom: 28px; }
.post-head h1 { font-size: 34px; line-height: 1.35; letter-spacing: -.5px; margin: 0 0 12px; }
.post-meta { color: var(--muted); font-size: 14px; }
.post-cover { width: 100%; border-radius: var(--radius); margin-bottom: 28px; display: block; }
.page-article { max-width: 800px; }
.post-body { font-size: 16.5px; }
.post-body h2 { font-size: 24px; margin: 40px 0 14px; }
.post-body h3 { font-size: 19px; margin: 30px 0 10px; }
.post-body p { margin: 0 0 18px; }
.post-body img { border-radius: 8px; }
.post-body pre { background: #0f172a; color: #e2e8f0; padding: 18px 20px; border-radius: 10px; overflow-x: auto; font-size: 13.5px; }
.post-body code { background: var(--surface); padding: 2px 6px; border-radius: 4px; font-size: .89em; }
.post-body pre code { background: none; padding: 0; color: inherit; }
.post-body blockquote { margin: 22px 0; padding: 4px 0 4px 18px; border-left: 3px solid var(--accent); color: var(--muted); }
.post-body table { width: 100%; border-collapse: collapse; margin: 22px 0; font-size: 14.5px; display: block; overflow-x: auto; }
.post-body th, .post-body td { border: 1px solid var(--line); padding: 9px 12px; text-align: left; }
.post-body th { background: var(--surface); }
.post-body ul, .post-body ol { padding-left: 22px; margin: 0 0 18px; }

/* chips */
.chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 18px; }
.chip { display: inline-block; padding: 3px 11px; border-radius: 999px; background: #eef4fb; color: var(--brand); font-size: 12.5px; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 999px; background: #fff7ed; color: #c2410c; font-size: 12.5px; }

/* 分页 */
.pagination { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 44px; }
.page-btn { display: inline-flex; align-items: center; justify-content: center; min-width: 38px; height: 38px; padding: 0 13px; border: 1px solid var(--line); border-radius: 8px; font-size: 14px; color: var(--fg); }
.page-btn:hover { border-color: var(--brand); color: var(--brand); text-decoration: none; }
.page-btn.current { background: var(--brand); border-color: var(--brand); color: #fff; }
.page-info { margin-left: auto; font-size: 13.5px; color: var(--muted); }

/* 页脚三列 */
.site-footer { background: #0b1c2c; color: rgba(255,255,255,.72); margin-top: 40px; }
.footer-inner { max-width: var(--maxw); margin: 0 auto; padding: 56px 24px 36px; display: grid; grid-template-columns: 1.6fr 1fr 1fr; gap: 40px; }
.footer-col h4 { color: #fff; font-size: 14px; letter-spacing: .5px; margin: 0 0 16px; font-weight: 600; }
.footer-col ul { list-style: none; padding: 0; margin: 0; font-size: 14px; }
.footer-col li { margin: 9px 0; }
.footer-col a { color: rgba(255,255,255,.72); }
.footer-col a:hover { color: #fff; }
.footer-brand { color: #fff; font-weight: 700; font-size: 17px; margin: 0 0 10px; }
.footer-brand-col p { margin: 0; font-size: 14px; opacity: .72; }
.footer-bottom { border-top: 1px solid rgba(255,255,255,.12); max-width: var(--maxw); margin: 0 auto; padding: 18px 24px 26px; display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.footer-bottom a { color: rgba(255,255,255,.6); }
.muted { color: var(--muted); }
.site-footer .muted { color: rgba(255,255,255,.6); }
.small { font-size: 12.5px; }
.empty { color: var(--muted); padding: 48px 0; text-align: center; }

/* 404 */
.notfound { text-align: center; padding: 90px 0; }
.notfound h1 { font-size: 76px; margin: 0 0 10px; color: var(--line); letter-spacing: 3px; }

@media (max-width: 760px) {
  .hero-inner { padding: 56px 20px 62px; }
  .hero h1 { font-size: 29px; letter-spacing: -.3px; }
  .hero-sub { font-size: 16px; }
  .header-inner { min-height: 58px; gap: 14px; padding: 0 20px; }
  .nav { gap: 14px; font-size: 14px; }
  .header-actions { gap: 12px; }
  .footer-inner { grid-template-columns: 1fr; gap: 28px; padding: 40px 20px 24px; }
  .post-head h1 { font-size: 26px; }
  .container { padding: 0 20px; }
  .cards { grid-template-columns: 1fr; }
  .page-info { width: 100%; margin-left: 0; }
}
"""

WIDGET_STATS_HTML = """<style>
/* 组件自带样式：宿主页只做 reset，视觉归组件自己。
   变量 --cms-accent 由 stats.js 按参数注入，所以颜色能跟着主题设置走。 */
.cms-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
  gap: 8px 12px;
  margin-top: 34px;
  padding-top: 26px;
  border-top: 1px solid rgba(255, 255, 255, 0.16);
}
.cms-stat { text-align: center; }
.cms-stat b {
  display: block;
  font-size: 32px;
  font-weight: 700;
  line-height: 1.1;
  color: var(--cms-accent, #f59e0b);
  font-variant-numeric: tabular-nums;
}
.cms-stat span {
  display: block;
  margin-top: 6px;
  font-size: 13px;
  letter-spacing: 0.04em;
  opacity: 0.72;
}
@media (max-width: 560px) {
  .cms-stat b { font-size: 26px; }
}
</style>
<div class="cms-stats" id="cms-stats"></div>
"""

WIDGET_STATS_JS = """(function () {
  // 沙箱内脚本：opaque origin，读不到 cookie、碰不到父页面 DOM。
  // 参数由宿主页塞进 #cms-widget-data（不执行，CSP 也不需要为它放行）。
  var root = document.getElementById('cms-stats');
  if (!root) return;

  var cfg = {};
  try {
    cfg = JSON.parse(document.getElementById('cms-widget-data').textContent || '{}');
  } catch (e) {
    cfg = {};
  }
  if (cfg.accent) root.style.setProperty('--cms-accent', String(cfg.accent));

  var items = Array.isArray(cfg.items) ? cfg.items : [];

  function text(v, d) {
    return d > 0 ? v.toFixed(d) : String(Math.round(v));
  }

  items.slice(0, 6).forEach(function (it) {
    var to = Number(it && it.value);
    if (!isFinite(to)) to = 0;
    var suffix = (it && it.suffix) ? String(it.suffix) : '';
    var decimals = to % 1 !== 0 ? 1 : 0;

    var box = document.createElement('div');
    box.className = 'cms-stat';
    var num = document.createElement('b');
    var label = document.createElement('span');
    num.textContent = text(0, decimals) + suffix;
    label.textContent = (it && it.label) ? String(it.label) : '';
    box.appendChild(num);
    box.appendChild(label);
    root.appendChild(box);

    // 组件是懒加载的（iframe loading=lazy），进视口时才开始跑，不用再做一轮观察
    var t0 = null;
    var dur = 900;
    function step(ts) {
      if (t0 === null) t0 = ts;
      var p = Math.min((ts - t0) / dur, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      num.textContent = text(to * eased, decimals) + suffix;
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  });
})();
"""

FILES: dict[str, str] = {
    "theme.json": MANIFEST_JSON,
    "layout.html": LAYOUT,
    "list.html": LIST,
    "page.html": PAGE,
    "partials/header.html": HEADER,
    "partials/footer.html": FOOTER,
    "partials/card.html": CARD,
    "widgets/stats.html": WIDGET_STATS_HTML,
    "widgets/stats.js": WIDGET_STATS_JS,
    "assets/style.css": STYLE,
}
