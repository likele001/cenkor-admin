# 主题模板开发

前台 HTML 由 **Jinja2 主题**渲染，模板存在数据库里，在后台「CMS → 模板工作台」直接改、实时预览、一键回滚。
内置主题由 12 个文件组成；你自己建主题时只覆盖想改的那几个即可，其余自动继承。
整个主题可以导出成 zip 搬到别的站点。

> **这是用户手册，不是框架文档。** 你只需要会 HTML + 一点 Jinja 语法。
> 数据从哪来、能调什么、哪里会报错，下面全部写清。

> **「标签」就是函数和过滤器。** 这套系统没有 `{dede:arclist}`、`[gallery]` 那种短代码，
> 也没有 `<?php ?>`。所有数据都靠第五节那 16 个**函数**取、第六节那 16 个**过滤器**加工，
> 写法就是普通的 Jinja 表达式。
>
> 记不住名字不用背：**后台「CMS → 模板工作台 → 标签速查」**里点一下就能插进模板，
> 支持按名字或用途搜（搜「分页」「日期」都行）。

---

## 一、模板与页面的对应关系

| 访问路径 | 用哪个模板 | 说明 |
|---|---|---|
| `/article/{slug}.html` | `detail.html` | 文章详情 |
| `/product/{slug}.html` | `detail.html` | 产品详情 |
| `/case/{slug}.html` | `detail.html` | 案例详情 |
| `/news/{slug}.html` | `detail.html` | 新闻详情 |
| `/p/{slug}.html` | `page.html` | 单页（关于我们 / 联系我们这类独立页面） |
| `/article/`、`/article/page/2/` | `list.html` | 文章列表（分页 12 条/页） |
| `/product/` | `list.html` | 产品列表 |
| `/case/` | `list.html` | 案例列表 |
| `/news/` | `list.html` | 新闻列表 |
| `/category/{slug}/`、`/category/{slug}/page/2/` | `list.html` | 分类列表 |
| `/tag/{slug}/`、`/tag/{slug}/page/2/` | `list.html` | 标签列表 |
| `/search/?kw=xxx` | `list.html` | 搜索结果 |
| 任何不存在的页面 | `404.html` | 返回 404 状态码 |

**分页一律走路径式**：第 2 页是 `/article/page/2/`，不是 `/article/?page=2`。老地址和 `/article/page/1/` 都会 301 到规范地址，页码非数字直接 404 —— 这条路径是固定的，模板里照此拼链接即可。

> `/news`（无斜杠）和 `/news/{slug}`（无 `.html`）是既有的 **JSON 接口**，给前端和
> AI 助手读数据；`/news/` 和 `/news/{slug}.html` 才是给人看的页面。同一段 URL 模式
> 由后端按后缀分流，两种都保留。

`layout.html`、`partials/*`、`macros/*`、`assets/style.css` 是所有页面的组成部分，改它们立刻生效。

### 列表页和详情页的差别

`list.html` 里 `item` 是 `None`、`items` 有数据、`page.pagination` 是真实分页对象；
`detail.html` 里反过来。同一个 `page` 对象，字段完全同构，只是 `page.kind` 不同
（`list` vs `article`/`product`/……）。所以你可以让两个模板共用一套 header 和卡片。

### 部署前提：nginx 必须把这些路径转给后端

官网是纯静态站，nginx 用 `try_files` 兜底。**少一条代理规则，对应页面就会静默返回
官网首页（状态码还是 200）**，看起来像「点了没反应」，极难排查。

所有**页面**统一转到 `/api/v1/page`，不要转到 `/api/v1/public`：

| 路径 | 目标 |
|---|---|
| 任何页面地址 | `/api/v1/page$uri$is_args$args` |
| `/sitemap.xml`、`/llms.txt` | 同名后端路径（同上，走 `/api/v1/page` 前缀） |
| `/api/v1/...` | JSON 接口，原样转发 |
| `/lp/...` | 落地页构建器，走 `/api/v1/public/lp/` |

**为什么页面不能转 `/api/v1/public`**：那是 JSON 接口的地盘。用户把内容地址配成
`/site`、`/news`、`/products`、`/search` 时，转发过去会撞上同名 JSON 接口 ——
浏览器拿到一段 JSON、状态码还是 200，页面错乱且日志里一条错都没有。
`/api/v1/page` 下只挂页面处理器，没有 JSON 路由，撞不上。

**不要为详情页写死前缀**（比如 `location ~ ^/(article|product|news|case|p)/`）：
地址规则在后台可配（见第九·补节），前缀本身是可变的。写死的结果是「后台配了规则，
新地址不走这条 location，直接落进兜底」或者更糟 —— 读到上一次落盘的陈旧 HTML。

参考配置（宝塔站点配置，不在仓库内）：

```nginx
# 页面全部回源后端，未知路径真 404（不要兜底到 /index.html，那是软 404）
location / {
    try_files $uri $uri/ @cms_page;
}

location @cms_page {
    proxy_pass http://127.0.0.1:8002/api/v1/page$uri$is_args$args;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

新环境部署时若发现页面变成官网首页，先查这个，不是模板问题。

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

## 二·补、从零做一个自己的主题（完整实战）

上一节只改了一句话。这一节从头做一个**完全不同风格**的主题，全程在后台点，不碰服务器、不重启。

目标：把默认的「白底蓝字单栏」改成杂志风 —— 大字品牌头、封面卡片、正文首字下沉。

### 动手前必须知道的三件事

**1. 首页不归主题管。**
`https://你的域名/` 是 nginx 直接吐的静态 `index.html`（官网那个文件），**不经过模板引擎**。
主题管的是「内容页」：文章/产品/案例/新闻的详情页、各类列表页、分类页、标签页、搜索页、404。

所以改了半天模板发现首页没变，不是没生效，是首页根本不在这套机制里。
想让首页也走模板，把首页指向一条 `page` 类型的内容，再把静态站的 `/` 转给后端（见第一节「部署前提」）。

**2. 主题是「覆盖」机制，不是「整套替换」。**
数据库里有的文件用你的，没有的自动回退到 `default` 主题。所以只改 3 个文件也算一个完整主题。

**3. 保存即生效，不用重启也不用手动清缓存。**
保存会同时清模板缓存，线上下一请求就是新版。

---

### 第 1 步：复制一份主题

后台 → **CMS → 模板工作台**（`/cms/templates`）→ 左侧文件树**最底部**的输入框，
填个主题名（只能小写字母数字加 `-` `_`，比如 `magazine`），点 **「从当前主题复制一份」**。

它会把当前主题的 12 个文件整份复制过来，然后切到新主题上编辑。

**为什么不从空白开始**：`layout.html`、`partials/meta.html`、`404.html` 这些是「漏一个就白屏或丢 SEO」的骨架。
从零写等于把踩坑机会乘以 12；复制一份只改想改的，其余自动跟随。

**复制完线上还没变。** 顶部主题下拉里能看到 `magazine`，但没有「· 生效中」标记 ——
现在只是在编辑它。要上线得做第 7 步。

顺手认识一下文件树那三个圆点：

| 圆点 / 标记 | 含义 |
|---|---|
| 蓝色 +「改」 | 数据库里有你改过的版本，正在生效 |
| 灰色 | 主题自带，内容和内置一致 |
| 浅灰 | 没动过，继承自 `default` |

---

### 第 2 步：先换配色

打开 `assets/style.css`，**只改最上面那段变量**就能整体换风格：

```css
:root {
  --bg: #fbf9f6;
  --fg: #171512;
  --muted: #7a7268;
  --line: #e6e0d8;
  --brand: #b4472a;
  --brand-soft: #fbeee9;
  --radius: 4px;
  --maxw: 1040px;
}

/* 深色模式：不想支持就删掉这三条 */
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14120f; --fg: #f0ece6; --muted: #9c9388;
    --line: #2c2823; --brand: #e0704f; --brand-soft: #2a1c17;
  }
}
```

右侧预览区大约 0.8 秒后自动变色。

> **这个文件会被整段塞进 `<style>` 标签**，所以里面不能出现 `</style>` 字样，
> 也不能用 `@import`（内联后失效）。要引外部字体就用 `<link>`，写在 `layout.html` 的 `{% block head %}` 里。

---

### 第 3 步：换掉站头

打开 `partials/header.html`，整份替换成：

```jinja
<header class="site-header">
  <div class="container header-inner">
    <a class="brand" href="{{ url('home') }}">
      <span class="brand-mark">{{ (site['brand.name'] or site.name or 'Cenkor') }}</span>
      {% if site['brand.slogan'] %}<span class="brand-slogan">{{ site['brand.slogan'] }}</span>{% endif %}
    </a>
    <nav class="nav">
      {% for item in nav('main') %}
        <a href="{{ item.url }}"{% if item.target and item.target != '_self' %} target="{{ item.target }}" rel="noopener"{% endif %}>{{ item.label }}</a>
      {% endfor %}
      <a href="{{ url('search') }}">搜索</a>
    </nav>
  </div>
</header>
```

三个要点：

- `url('home')` 生成站点根地址，**不要手写 `/`** —— 换域名、换子目录时会错
- `nav('main')` 返回菜单数组，每项是 `{label, url, target}`
- `site['brand.name']` 读站点配置里的品牌名；`site.name` 是兜底

再往 `assets/style.css` 末尾加：

```css
.header-inner { flex-direction: column; align-items: flex-start; gap: 6px; padding: 18px 0 12px; }
.brand { display: flex; align-items: baseline; gap: 12px; }
.brand-mark { font-size: 26px; font-weight: 800; letter-spacing: -0.6px; color: var(--fg); }
.brand-slogan { font-size: 13px; color: var(--muted); }
.nav { gap: 20px; font-size: 13.5px; letter-spacing: 0.3px; }
```

---

### 第 4 步：换卡片

`partials/card.html` 是**所有列表卡片**的唯一来源，循环变量固定叫 `r`：

```jinja
<a class="card" href="{{ r.url }}">
  {% if r.cover %}
    <div class="card-media">
      <img src="{{ r.cover|asset_url }}" alt="{{ r.title }}" loading="lazy">
      {% if r.category %}<span class="card-badge">{{ r.category.name }}</span>{% endif %}
    </div>
  {% endif %}
  <div class="card-body">
    <h3>{{ r.title }}</h3>
    {% if r.excerpt %}<p class="card-desc">{{ r.excerpt }}</p>{% endif %}
    {% if r.published_at %}<time class="card-date" datetime="{{ r.published_at }}">{{ r.published_at|date }}</time>{% endif %}
  </div>
</a>
```

**`r.cover` 可能是空串，必须用 `{% if %}` 包住**，否则会输出 `<img src="">`（浏览器会拿当前页地址当图片地址，多一次 404 请求）。

配套 CSS：

```css
.card { display: flex; flex-direction: column; border: 0; border-radius: var(--radius); overflow: hidden; background: transparent; }
.card-media { position: relative; aspect-ratio: 16 / 10; overflow: hidden; border-radius: var(--radius); }
.card-media img { width: 100%; height: 100%; object-fit: cover; transition: transform .4s ease; }
.card:hover .card-media img { transform: scale(1.04); }
.card-badge { position: absolute; left: 10px; top: 10px; padding: 2px 9px; border-radius: 999px;
  background: rgba(0,0,0,.62); color: #fff; font-size: 11.5px; }
.card-body { padding: 12px 2px 0; }
.card-body h3 { font-size: 16.5px; line-height: 1.45; margin: 0 0 6px; color: var(--fg); }
.card-desc { font-size: 13.5px; color: var(--muted); margin: 0 0 8px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card-date { font-size: 12px; color: var(--muted); letter-spacing: .4px; }
```

---

### 第 5 步：换详情页

`detail.html` 整份替换（注意里面 `|safe` 的位置，删了正文会变成一堆转义字符）：

```jinja
{% extends "layout.html" %}
{% block content %}
<article class="post">
  <header class="post-head">
    {% if item.category %}
      <a class="post-kicker" href="{{ item.category.url }}">{{ item.category.name }}</a>
    {% endif %}
    <h1>{{ item.title }}</h1>
    {% if item.excerpt %}<p class="post-lead">{{ item.excerpt }}</p>{% endif %}
    <div class="post-meta">
      {% if item.published_at %}<time datetime="{{ item.published_at }}">{{ item.published_at|date }}</time>{% endif %}
      {% if item.view_count %}<span>{{ item.view_count }} 次阅读</span>{% endif %}
      {% if item.ai_generated %}<span class="badge">AI 辅助 · 已人工审核</span>{% endif %}
    </div>
  </header>

  {% if item.cover %}<img class="post-cover" src="{{ item.cover|asset_url }}" alt="{{ item.title }}">{% endif %}

  <div class="post-body">{{ item.body_html|safe }}</div>

  {% if item.tags %}
    <div class="chips">
      {% for t in item.tags %}<span class="chip">{{ t }}</span>{% endfor %}
    </div>
  {% endif %}
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
```

`item.tags` 是**名称字符串数组**（`["智能制造", "案例"]`），不是对象，所以直接 `{{ t }}`，别写 `{{ t.name }}`。

首字下沉和导语样式：

```css
.post-head { margin-bottom: 26px; }
.post-kicker { font-size: 12px; letter-spacing: 1.4px; text-transform: uppercase; color: var(--brand); }
.post-head h1 { font-size: 34px; line-height: 1.28; margin: 8px 0 12px; letter-spacing: -0.5px; }
.post-lead { font-size: 17px; color: var(--muted); line-height: 1.7; margin: 0 0 14px; }
.post-body > p:first-of-type::first-letter {
  float: left; font-size: 54px; line-height: .92; padding: 4px 8px 0 0; font-weight: 700; color: var(--brand);
}
```

---

### 第 6 步：换列表页

`list.html` 同时服务**七种**页面（文章/产品/案例/新闻/分类/标签/搜索），靠 `page.title` 区分，不用写七套：

```jinja
{% extends "layout.html" %}
{% block content %}
<section class="section">
  <header class="list-head">
    <h1 class="section-title">{{ page.title }}</h1>
    {% if page.description %}<p class="section-desc">{{ page.description }}</p>{% endif %}
    <form class="list-search" action="{{ url('search') }}" method="get">
      <input type="search" name="kw" placeholder="搜索文章…" aria-label="搜索">
      <button type="submit">搜索</button>
    </form>
  </header>

  <div class="cards">
    {% for r in items %}
      {% include "partials/card.html" %}
    {% else %}
      <div class="empty">
        <p>这里还没有内容。</p>
        <p><a class="btn btn-primary" href="{{ url('home') }}">回首页看看</a></p>
      </div>
    {% endfor %}
  </div>

  {% include "partials/pagination.html" %}
</section>
{% endblock %}
```

`{% for ... %}{% else %}` 里的 `else` 是「一次都没循环」时执行 —— 空列表提示就靠它，不用另外判 `items|length`。

分页**不要自己拼 `?page=N`**，直接 include 那个 partial，里面的地址都是后端算好的绝对路径。

---

### 第 7 步：让线上用上它

顶部主题下拉选到 `magazine`，点 **「设为生效」**。

这是**整站级**切换：所有内容页立刻换版式。回退就是下拉切回 `default` 再点一次「设为生效」。

如果按钮是灰的，说明当前主题已经是生效主题（下拉里带「· 生效中」）。

---

### 第 8 步：上线前自检

做完对着这张表过一遍，每一条都能在预览里直接看：

| 检查项 | 怎么看 | 为什么重要 |
|---|---|---|
| `<title>` 正确 | 浏览器标签 / 预览区源码 | 别改成写死的站名，要用 `page.full_title` |
| `canonical` 在 | 看源码 `<link rel="canonical">` | 缺了会有重复页面问题 |
| `meta description` 在 | 看源码 | 搜索结果摘要 |
| `partials/meta.html` 没删 | 看 `layout.html` | OG / Twitter / JSON-LD 全在里面 |
| JSON-LD 在 | 源码搜 `application/ld+json` | 富摘要与 AI 引用准确度 |
| 正文没被转义 | 详情页看有没有 `&lt;p&gt;` | 少了 `\|safe` 的典型症状 |
| 图片都有 alt | 看 `card.html` / `detail.html` | 无障碍 + 图片 SEO |
| 空列表有提示 | 找一个没内容的分类 | 否则一片空白像坏了 |
| 手机上不横向滚动 | 预览区拉窄 | 定宽元素最常见 |

---

### 改坏了怎么退回去

| 情况 | 怎么办 |
|---|---|
| 单个文件改坏 | 编辑器右上 **「还原」**（只对「已覆盖」的文件有效；本来就是内置的会提示无需还原） |
| 语法写错存不进去 | 编辑器会标红并给出行列号；保存也会被拒，不会污染线上 |
| 整站版式乱了 | 顶部下拉切回 `default` → **「设为生效」** |
| 新主题彻底失败 | 「删除主题」，然后重新「从当前主题复制一份」 |

**「删除主题」不可恢复**，删之前先「导出 zip」留个底。

---

### 导出，搬去别的站

- **导出**：顶部 **「导出 zip」** → 拿到完整主题包
- **导入**：目标站点的模板工作台 → **「导入 zip」**

导入有四道闸：整包 5MB / 最多 300 个文件 / 单文件 1MB / 路径白名单。
而且**所有模板会先做一遍语法校验，错一处整包拒绝** —— 所以导不进去基本可以断定包里真有错，不是网络问题。

---

### 常见需求该改哪个文件

| 想要的效果 | 改这里 |
|---|---|
| 换整体配色 / 字号 / 圆角 | `assets/style.css` 的 `:root` |
| 换站头、导航、logo | `partials/header.html` |
| 换页脚、备案号、友链 | `partials/footer.html` |
| 换列表卡片样式 | `partials/card.html` |
| 换分页条样式 | `partials/pagination.html` |
| 详情页版式 | `detail.html` |
| 列表页（含分类/标签/搜索）版式 | `list.html` |
| 单页（关于我们等） | `page.html` |
| 404 页面 | `404.html` |
| 全站 `<head>`、字体、脚本 | `layout.html` 的 `{% block head %}` |
| 按钮、标签组这些可复用件 | `macros/ui.html` |

想加一个**主题级**的小组件（比如「回到顶部」按钮）：写进 `partials/footer.html`，
样式写进 `assets/style.css`，脚本用 `<script>` 内联在 footer 里 —— 没有单独的 js 文件入口。

> **预览区不执行脚本。** 右侧预览是个禁脚本的 iframe（防止模板里的脚本影响后台），
> 所以加了 JS 之后预览里看不到效果，**保存并打开线上页面**才能验证。
> CSS 和 HTML 的改动在预览里是实时的，只有 JS 需要这一步。

---

## 三、文件约定

### 目录结构

```
layout.html              布局骨架：<head>、header、<main>、footer，子模板 extends 它
detail.html              详情页（article / product / news / case 共用）
page.html                单页（关于我们 / 联系我们这类）
list.html                列表页（文章/产品/案例/新闻/分类/标签/搜索，七种共用）
404.html                 未找到（必须输出 404 状态码，否则爬虫会收录空页面）
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

下面列了 17 条：第 9 项 `site` 是预注入的 dict，不是函数，其余 16 个才是可调用的 API。

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

### 11. `pagination(page=1, total=0, per_page=20, window=5, base_path=None)` — 分页对象

返回：

```
{page, per_page, total, total_pages,
 window: [页码数组], has_prev, has_next, prev_page, next_page,
 range_start, range_end,
 # 下面五个只有传了 base_path 才有值，否则是 None：
 url, first_url, last_url, prev_url, next_url,
 pages: [{n, url, current}, ...]}
```

`base_path` 传列表基路径，生成的链接是**绝对地址**，可以直接当 href：

```jinja
{% set pg = pagination(1, 128, 12, 5, '/article/') %}
{{ pg.next_url }}   {# https://www.cenkor.cn/article/page/2/ #}
```

列表页直接用 `page.pagination` 即可，路由已经填好了 base_path。

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

传 `page=` 时，列表类（`article` / `product` / `news` / `case` / `category` / `tag`）生成路径式分页 `/article/page/2/`；`search` 仍是 `&page=N`（关键词在 query 上，页码塞不进路径）。详情页传 `page=` 会被忽略。

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

## 六·补、找不到你要的标签怎么办

按顺序试，通常第一步就解决了。

### 1. 先看有没有

「模板工作台 → 标签速查」有搜索框，按**用途**搜比按名字搜更快：搜「分页」「日期」「图片」「搜索」都能命中。

### 2. 只是形式不同 → 换写法

很多「缺标签」其实是同一个东西换个姿势：

| 你想要 | 实际怎么写 |
|---|---|
| 首页最新 6 条 | `content_list('article', limit=6)` |
| 某个栏目的 8 条 | `content_list('article', limit=8, category='news')` |
| 带某个标签的条目 | `content_list('article', tag='智能制造')` |
| 按阅读数排序 | `content_list('article', sort='-view_count')` |
| 排除当前这篇 | `related(item, limit=4)` |
| 全站搜关键词 | `search('关键词')` |
| 面包屑 | `{{ item.category.name }}`（再往上一层没有现成字段） |
| 上一篇 / 下一篇 | ❌ 没有现成标签，用 `related(item, limit=4)` 代替 |
| 站点名 / 域名 | `{{ site.name }}` / `{{ site.domain }}` |
| 当前年份 | `{{ now\|date('%Y') }}` |
| 正文纯文字摘要 | `{{ item.body_html\|excerpt(120) }}` |

`content_list` 的完整参数（`type` / `limit` / `offset` / `category` / `tag` / `sort` / `exclude`）
在第 5 节第 1 条，绝大多数列表需求都在它里面。

### 3. 只是重复片段 → 用 `macro` 自己造

页面里反复出现的结构（卡片、标签云、价格块），写成 `macro` 就是你的自定义标签：

```jinja
{# 放在 macros/card.html #}
{% macro card(r, show_date=true) %}
  <article class="card">
    {% if r.cover %}<img src="{{ r.cover }}" alt="{{ r.title }}" loading="lazy">{% endif %}
    <h3><a href="{{ r.url }}">{{ r.title }}</a></h3>
    {% if show_date %}<time>{{ r.published_at|date }}</time>{% endif %}
    <p>{{ r.excerpt }}</p>
  </article>
{% endmacro %}
```

```jinja
{# 在 layout.html 或其他模板里 #}
{% from 'macros/card.html' import card %}

{% for r in content_list('article', limit=6) %}{{ card(r) }}{% endfor %}
{% for r in related(item, limit=3) %}{{ card(r, show_date=false) }}{% endfor %}
```

要点：

- 放在 `macros/` 目录，用 `{% from 'xxx' import 名字 %}` 引入
- 参数默认值、`if` 判断都能用，跟普通 Jinja 一样
- 沙箱**放行 macro 调用**，这是不改后端就能造标签的唯一方式
- macro 里同样能调 16 个数据 API 和过滤器

### 4. 需要新数据源 → 找开发写 `template_tags.py`

如果是「App 里有、模板拿不到」的数据（比如 App 自己的表），让开发者在该 App 目录下加
`template_tags.py`，声明 `FUNCTIONS` / `FILTERS`，重启后端自动生效。
写法见开发文档 [dev_guide.md](dev_guide.md) 的「站点模板标签」一节。

注册好后，这些标签会**自动出现在「标签速查」面板里**，不用记名字。

### 5. 还是不行 → 别硬凑

模板只能读、不能写，也不能发外部请求。下面这些**做不了**，不用试：

- 提交表单、写库、改内容（放进模板也不会执行）
- 调第三方 API 拿数据（沙箱不给你网络）
- 读文件、执行命令
- 遍历超过上限的数据（`limit` 会被夹住）

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

`partials/pagination.html` 用 `page.pagination`，直接取 `pg.prev_url` / `pg.next_url` /
`pg.pages[].url`，都是后端算好的绝对地址 —— 不要自己拼 `?page=N`，那样会被 301，
多一跳且爬虫收不到规范地址。

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

## 九·补、URL 伪静态规则（后台可配）

模板里拿到的 `page.url` / `entry.url` 不是硬编码的，是**按后台配的规则现算**的。
规则变了，模板不用改，地址跟着变。

### 四层规则，优先级从高到低

| 层 | 存在哪 | 配在哪 | 管什么 |
|---|---|---|---|
| 1 单条钉死 | `cms_entries.url_path` | 文章编辑页「自定义地址」 | 就这一条内容，规则再改也不动它 |
| 2 栏目覆盖 | `cms_categories.url_pattern` | 分类管理 → 编辑栏目 | **只管这个栏目页自己的地址** |
| 3 标签覆盖 | `cms_tags.url_pattern` | 标签管理 → 编辑标签 | **只管这个标签页自己的地址** |
| 4 站点默认 | `cms_site_config['url.*']` | 站点配置 → URL 规则 | 全站通用 |

⚠️ **最容易搞混的一点**：栏目级规则**不管**该栏目下文章的地址。
文章要不要带栏目目录（`/mes/quality/xxx.html` 还是 `/xxx.html`），
看的是站点默认规则里有没有用 `{catdir}`。早期版本把栏目规则当详情页模板用，
会导致配了规则的栏目下所有条目反解时拿内容 slug 查栏目表 → 整批 404。

### 规则可用变量

| 变量 | 含义 | 可用于 |
|---|---|---|
| `{type}` | 内容类型前缀（article/product/news/case/p） | 详情、栏目、标签、列表 |
| `{catdir}` | 栏目完整目录链（`mes/quality`） | 详情、栏目 |
| `{cat}` | 栏目自身 slug | 详情、栏目 |
| `{parent}` | 父栏目目录链（不含自身） | 栏目 |
| `{slug}` | 内容 / 栏目 / 标签的别名 | 详情、栏目、标签 |
| `{id}` | 记录 ID | 详情、栏目、标签 |
| `{year}` `{month}` `{day}` | 发布日期 | 详情 |

规则里必须至少有一个能唯一定位内容的变量（`{slug}` 或 `{id}`），
否则所有内容会指向同一个地址 —— 后台保存时会直接拒掉。

### 内置默认规则

```
article / product / news / case   {type}/{slug}.html
page                              p/{slug}.html
category                          category/{slug}/
tag                               tag/{slug}/
列表页                             {type}/
```

### 改规则会发生什么

1. 旧规则被存档到 `cms_site_config['url.history']`（最多 50 条）
2. 已收录的老地址 **301** 到新地址，不是 404
3. 页面上的 `canonical` 自动收敛到当前规则算出的地址

改完规则后如果发现「新地址 404、老地址不跳」，多半是缓存：
规则缓存 TTL 是 2 秒，等一下就好。

### 后台 API

| 接口 | 用途 |
|---|---|
| `GET /api/v1/cms/url-rules` | 列出全部规则（默认 + 栏目覆盖 + 标签覆盖 + 历史） |
| `POST /api/v1/cms/url-rules/preview` | 预览一条规则：示例地址 + 冲突检测 |
| `POST /api/v1/cms/url-rules/save` | 保存站点默认规则（空串 = 恢复内置默认） |
| `POST /api/v1/cms/url-rules/resolve` | 按当前规则算某条内容的规范地址（编辑页实时预览用） |

`preview` 会把待保存的规则和现有全部规则对撞：
同层级同类型的冲突（`block`）保存时会被拒，跨层级的重叠（`warn`）只提醒 —— 
后者是设计好的覆盖关系，不是错误。


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


---

## 十四、静态落盘（已默认关闭，别急着开）

详情页是流量主体，每开一次都要查数据 + 渲染。这层功能把渲染结果落成静态 HTML，
nginx `try_files` 命中就直接出，同一页渲染过一次不再进 Python。

**但它在当前版本里默认是关的，而且不建议开。** 原因很实在：

地址规则现在后台可配（第九·补节）。落盘文件的路径是「当时那套规则」算出来的，
一旦改了规则，磁盘上的旧文件还在原处 ——

- 新地址没有对应文件 → 回源渲染，正常
- **老地址的文件还在 → nginx 直接供应上去，内容陈旧、你还以为规则没生效**
- 更麻烦的是把内容下线（到期归档、改状态为草稿）后，文件仍在，线上照样 200 返回全文

这不是理论风险，是真实发生过的线上故障。

### 如果你确实需要它

先确认这三件事都能接受，再动手：

1. 地址规则近期不会改（或者每次改完都手动清缓存）
2. 内容下线流程里有额外的清缓存步骤
3. 你有办法验证「线上返回的就是库里最新的」

开启方式（后端 `.env`）：

```
CMS_STATIC_CACHE=1
CMS_STATIC_CACHE_ROOT=/www/wwwroot/cenkor-admin/backend/var/htmlcache
```

改完重启后端（宝塔会自动接管端口，不要手工 nohup）。

nginx 侧只需要一条**不写死地址前缀**的规则，`root` 里的域名目录必须等于实际访问的 Host：

```nginx
location / {
    root /www/wwwroot/cenkor-admin/backend/var/htmlcache/www.cenkor.cn;
    try_files $uri $uri/ @cms_page;
    expires 300s;
}
```

后端只在**站点规范域名**下落盘。用 IP、localhost、内网域名访问时不落盘 ——
那些请求渲染出的 canonical / og:url 是错的，写进文件会把全站 SEO 打脏。

### 什么时候自动失效

| 操作 | 失效范围 |
|---|---|
| 保存条目（正文、标题、SEO、分类、标签、状态） | 该条目的详情页 |
| 改 slug | 旧地址 + 新地址 |
| 删除 / 批量删除 / 批量改状态 | 涉及的条目 |
| 审核通过或驳回、版本回滚、批量导入 | 涉及的条目 |
| 分类或标签改名（会进面包屑与 chip） | **整站** |
| 保存模板 / 切主题 / 导入主题包 | **整站** |
| 改站点域名或品牌名 | 该站点 |

**改地址规则不在上面这张表里** —— 这是它最大的坑。改规则后必须手动清：

```bash
cd /www/wwwroot/cenkor-admin/backend
python3 scripts/build_static_cache.py --purge
```

### 运维命令

```bash
python3 scripts/build_static_cache.py --stats         # 文件数、占用、开关状态
python3 scripts/build_static_cache.py --purge         # 清空全部
python3 scripts/build_static_cache.py --purge-entry <slug>
python3 scripts/build_static_cache.py --warm https://www.cenkor.cn   # 按 sitemap 预热
```

清空是安全且幂等的：nginx 全部 miss → 回落动态渲染 → 顺手重新落盘。

### 回退

**只改 `.env` 不够。** 磁盘上的旧文件 nginx 照样会读，结果就是「已经改了模板/规则，
线上永远旧版」。完整回退两步：

1. `.env` 改 `CMS_STATIC_CACHE=0`，重启后端
2. `python3 scripts/build_static_cache.py --purge`

### 排错

| 现象 | 原因 |
|---|---|
| 改了内容，线上还是旧的 | 开关还开着且文件没清（用 `--stats` 看）／nginx `root` 的域名目录与实际 Host 不一致 |
| 改了地址规则，老地址还能打开 | 落盘文件没清 —— 见上一节 |
| 开了但一点没快 | 后端只在规范域名下落盘，用 IP 或 localhost 预热无效 |
| 目录里一个文件都没有 | `cms_sites.domain` 和 `cms_site_config['brand.domain']` 都没配 |

### 目录长什么样

```
backend/var/htmlcache/
└── www.cenkor.cn/
    ├── article/tech-doc-length.html
    ├── case/discrete-vs-process-mes.html
    └── product/lightmes.html
```

`backend/var/` 已进 `.gitignore` —— 这是机器本地状态，换台机器会自己重建。
