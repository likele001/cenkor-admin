# Cenkor Admin · 宝塔 Nginx 反代与伪静态配置说明

本文只讲 nginx 层的一件事:**一个请求进来,该交给谁**——哪些路径反代到后端、哪些路径直出静态文件、SPA 回退怎么写。核对时间 2026-11-04,以下代码块逐条对照线上 `/www/server/panel/vhost/nginx/` 实际配置抄录。

> 分工边界:端口台账与服务进程见 [deploy.md](deploy.md)(**唯一权威**),域名解析与 SSL 见 [domain_setup.md](domain_setup.md),把系统交付到别的机器的完整流程见 [baota_static_deploy.md](baota_static_deploy.md)。本文不重复这些内容。

---

## 0. 先记住三条

1. **前端是纯静态,nginx 直出 `dist`;只有 `/api/` 和少数动态路径反代到 `127.0.0.1:8002`。** 绝不整站 `proxy_pass /`,否则静态资源、长缓存、独立子站全被吞掉。
2. **server 级 `rewrite` 在 `location` 匹配之前执行。** 伪静态里的 SPA 回退只要没排除 `/api/`,请求就会被 rewrite 成 `/index.html`——`location /api/` 反代写得再对也走不到。这是本项目踩过两次的坑。
3. **宝塔面板的「伪静态」「反向代理」页面一保存,会重写 `rewrite/` 和 `proxy/` 下的 conf。** 手工改之前先备份,改完别在面板里随手点保存,自定义注释和规则可能被覆盖回去。

---

## 1. 站点全景

| 域名 / 路径 | 站点根目录(root) | 反代到后端 | 伪静态(SPA 回退) | 说明 |
|---|---|---|---|---|
| `admin.cenkor.cn` | `cenkor-admin/frontend/admin-web/dist` | `/api/`、`/api/v1/cms/ai/`、`/api/v1/ws/`、`/.app-assets/` → `:8002` | 有,排除项最多 | 管理后台 SPA |
| `admin.cenkor.cn/landing/` | `cenkor-admin/frontend/landing/` | **无** | 有(`^~ /landing/` 优先) | 官网 + 文档中心,同域下的独立静态子站 |
| `portal.cenkor.cn` | `cenkor-admin/frontend/portal-web/dist` | `/api/`、`= /llms.txt` → `:8002` | 有(本次修复过) | 用户中心 / 应用中心 SPA |
| `dev.cenkor.cn` | `cenkor-admin/frontend/developer-web/dist` | `/api/` → `:8002`(由**宝塔反向代理面板**生成) | 有(最简版) | 开发者门户 SPA |
| `www.cenkor.cn` | `/www/wwwroot/website`(**外部站,不属本仓库**) | `/api/` + 一批 CMS 动态页 + `@cms_dynamic` 兜底 → `:8002` | **无**(rewrite 文件为空,用 `try_files` 命名 location) | 品牌官网,CMS 整页渲染 |
| `docs.user.023ent.net`<br>`docs.cenkor.cn` | `knowledge/docs/.vitepress/dist` | **无** | **无**(rewrite 文件为空) | VitePress 知识库,纯静态 |

后端只有一个:宝塔「Python 项目」`cenkor`,uvicorn 监听 `127.0.0.1:8002`。所有反代目标都是它。

---

## 2. 什么时候反代:判定规则

### 2.1 一句话口诀

> **URL 对应磁盘上真实文件 → nginx 直出;否则先问「是不是 API / 动态内容」,是就反代,不是才做 SPA 回退。**

### 2.2 逐场景对照

| 场景 | 处理方式 | 线上例子 |
|---|---|---|
| 前端同域调后端接口 | **反代** `location /api/` | 所有站点,避免 CORS 与跨域 cookie 问题 |
| WebSocket 长连接 | **反代** + `Upgrade` 头 + 超长超时 | `admin` 的 `/api/v1/ws/`,`read_timeout 86400s` |
| AI 生成类长请求 | **反代** + 600s 超时 + 关缓存 | `admin` 的 `/api/v1/cms/ai/`(实测 112s,默认 60s 会被掐成 504) |
| 后端动态生成的文本 | **精确 location 反代** | `/llms.txt`、`/sitemap.xml` → `/api/v1/public/...` |
| CMS 动态页(静态文件不存在) | **`try_files` 末尾命名 location 反代** | `www` 站的 `@cms_dynamic` → `/api/v1/page$uri` |
| 后台托管的插件静态资源 | **反代**(文件不在前端 dist) | `admin` 的 `/.app-assets/` |
| 前端构建产物 `/assets/*` | **不反代**,直出 + 365d 长缓存 | 所有 SPA |
| 入口 `index.html` | **不反代**,直出 + 不缓存 | 保证发版立即生效 |
| 独立静态子站 `/landing/`、VitePress 文档站 | **不反代** | `root` + `try_files` |

### 2.3 什么时候**不要**反代

- **不要整站 `proxy_pass http://127.0.0.1:8002;`**:后端不托管前端 dist,会把 `/assets/`、路由页、静态子站全打成 404。
- **不要把 `/landing/` 反代**:它是 `frontend/landing/` 下的预渲染 HTML,nginx `try_files $uri $uri.html` 就能直接命中。
- **不要把知识库站反代**:`docs.user.023ent.net` 是 VitePress 产物,零后端依赖。
- **不要为了「修一个 404」就加反代**:先看请求该不该落到磁盘文件,多数是伪静态排除项漏了。

### 2.4 容易混淆:反代 ≠ 后端上游地址

后端自己也会作为客户端去请求「官方应用市场目录」。那是 **`.env` 里的 `MARKET_HUB_URL`**,和 nginx 反代无关:

```dotenv
# /www/wwwroot/cenkor-admin/backend/.env
# 商店 API 实际挂在 dev.cenkor.cn;portal.cenkor.cn 是纯前端 SPA,写它会拿到 HTML 首页
MARKET_HUB_URL=https://dev.cenkor.cn
```

曾经 `/api/v1/cms/theme-market/catalog` 报「官方应用市场返回了非 JSON 内容」,根因就是这个变量没配、回退默认 `https://portal.cenkor.cn`,后端把 SPA 首页当 JSON 解析。**看到「非 JSON 内容」先分清是浏览器→nginx 这一段,还是后端→外部服务那一段。**

---

## 3. 反代代码(可整段复制)

### 3.1 通用 `/api/` 模板(portal / admin / www 同款)

```nginx
location /api/ {
    client_max_body_size 50m;
    proxy_pass http://127.0.0.1:8002/api/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

> `proxy_pass` **带** `/api/` 结尾时,location 前缀会被替换掉;`/api/v1/store/apps` → 后端 `/api/v1/store/apps`。写成不带路径的 `proxy_pass http://127.0.0.1:8002;` 则会把完整 URI 原样传过去,两者不能混用。

### 3.2 admin 站全套(四种反代)

```nginx
# AI 长请求:落地页子站实测 112s,全局默认 60s 会掐成 504
location /api/v1/cms/ai/ {
    proxy_pass http://127.0.0.1:8002;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
    proxy_cache off;
}

# 常规接口
location /api/ {
    client_max_body_size 50m;
    proxy_pass http://127.0.0.1:8002/api/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# WebSocket
location /api/v1/ws/ {
    proxy_pass http://127.0.0.1:8002/api/v1/ws/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_read_timeout 86400s;
}

# 应用插件静态资源(由后端托管,不在前端 dist)
location /.app-assets/ {
    expires 365d;
    proxy_pass http://127.0.0.1:8002;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

> nginx 中 `location /api/v1/cms/ai/` 与 `/api/v1/ws/` 是**更长的前缀**,优先于 `/api/`,所以顺序无所谓;但要保证它们写在 `location /` 的 SPA 兜底之前。

### 3.3 dev 站:宝塔「反向代理」面板生成的写法

`dev.cenkor.cn` 的 `/api/` 不在主 vhost 里,而是主配置 `include /www/server/panel/vhost/nginx/proxy/dev.cenkor.cn/*.conf;` 引入的:

```nginx
# /www/server/panel/vhost/nginx/proxy/dev.cenkor.cn/e77989ed..._dev.cenkor.cn.conf
#PROXY-START/

# 后端 API 反代
location /api/ {
    proxy_pass http://127.0.0.1:8002/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header REMOTE-HOST $remote_addr;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_http_version 1.1;
    client_max_body_size 50m;
}

#PROXY-END/
```

`$connection_upgrade` 由全局 map 提供,**不在本文件里**:

```nginx
# /www/server/panel/vhost/nginx/0.websocket.conf
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''  close;
}
```

> 两种写法可以共存,但别在同一个站点重复定义 `location /api/`(nginx 启动报 `duplicate location`)。admin / portal / www 是**手写进主 vhost** 并把 `# include .../proxy/*.conf` 注释掉的;dev 是**走面板**的。排查时先看主 vhost 有没有那行 include。

### 3.4 portal 站:动态 `llms.txt`

```nginx
# AI 答案引擎的内容目录,动态生成走 CMS 后端
location = /llms.txt {
    proxy_pass http://127.0.0.1:8002/api/v1/public/llms.txt;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

精确匹配 `= /llms.txt` 必须在伪静态排除清单里(见 §4.2),否则会被 SPA 回退抢走。

### 3.5 www 站:CMS 整页渲染 + 动态兜底

官网是纯静态站,但 CMS 的列表页 / 落地页由后端整页渲染,静态文件不存在时不能兜 `index.html`:

```nginx
# 典型列表页(短路径,直接反代)
location = /article/ {
    proxy_cache off;
    proxy_no_cache 1;
    proxy_pass http://127.0.0.1:8002/api/v1/page/article/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 30s;
}

# AI 落地页,整页由后端渲染(SEO head / JSON-LD / 表单)
location ^~ /lp/ {
    proxy_cache off;
    proxy_no_cache 1;
    proxy_pass http://127.0.0.1:8002/api/v1/public/lp/;
    proxy_read_timeout 30s;
}

# 静态优先,未命中回源后端按 URL 规则反解
location @cms_dynamic {
    proxy_cache off;
    proxy_no_cache 1;
    proxy_pass http://127.0.0.1:8002/api/v1/page$uri$is_args$args;
    proxy_set_header Host $host;
    proxy_read_timeout 30s;
}

location / {
    try_files $uri $uri/ $uri.html $uri/index.html @cms_dynamic;
}
```

> ⚠️ `location /` 最后**不能**兜 `/index.html`:任何未知路径都会返回官网首页 + 200,爬虫当成软 404 收录一堆重复页,SEO 直接废掉。这个站因此**不写 SPA 回退伪静态**。

### 3.6 不反代:独立静态子站与文档站

```nginx
# admin.cenkor.cn —— 官网 / 文档中心,同域下的独立静态子站
location ^~ /landing/ {
    root /www/wwwroot/cenkor-admin/frontend/;
    try_files $uri $uri.html $uri/ /landing/index.html;
    add_header Cache-Control "no-cache";
}
location = /landing { return 301 /landing/; }

# admin.cenkor.cn —— 入口 HTML 不缓存,构建产物长缓存
location /assets/   { expires 365d; }
location = /index.html { expires -1; }
location / { try_files $uri $uri/ /index.html; }

# docs.user.023ent.net —— VitePress cleanUrls,纯静态零反代
location / {
    try_files $uri $uri.html $uri/index.html =404;
}
```

`$uri.html` 让 `/landing/docs` 命中预渲染的 `docs.html`;知识库同理支持无 `.html` 后缀的 cleanUrls。

### 3.7 反代头与超时速查

| 项 | 值 | 为什么 |
|---|---|---|
| `proxy_http_version` | `1.1` | keep-alive 与 WebSocket 需要 |
| `Host` / `X-Real-IP` / `X-Forwarded-For` / `X-Forwarded-Proto` | 全带 | 后端生成绝对 URL、限流、审计日志都依赖 |
| `client_max_body_size` | `50m` | 应用包 / 主题包上传 |
| `proxy_read_timeout` | 常规默认 / AI `600s` / WS `86400s` | 按业务最长耗时 |
| `proxy_cache` | 动态页与 AI 请求 `off` | 避免把个性化 / 生成结果缓存住 |

---

## 4. 伪静态代码(SPA 回退)

### 4.1 为什么必须写

Vue 用 history 模式,`/system/apps`、`/apps` 这类路径在磁盘上不存在文件,nginx 默认会 404。宝塔站点默认只给 `try_files $uri $uri/ /index.html` 之类的粗规则,遇到「同域下还有 API 反代 + 独立子站 + 动态文本」就会出错,所以本项目用**伪静态里的 `if` + `rewrite` 显式控制**。

**核心风险:`rewrite` 属于 server 级的 rewrite 阶段,先于 `location` 匹配执行。** 一旦把 `/api/v1/store/apps` rewrite 成 `/index.html`,后面的 `location /api/` 反代根本没有机会参与。所以**排除清单必须和主 vhost 里所有反代 / 静态 location 一一对应**。

### 4.2 标准模板(portal 站,2026-11-04 修复后的正确版)

```nginx
# /www/server/panel/vhost/rewrite/portal.cenkor.cn.conf
# SPA 回退:排除 /api/ 与 /llms.txt,避免 API/AI 目录被 rewrite 到 index.html
set $spa_fallback 0;
if ($uri !~ ^/(api/|llms\.txt)) {     # ← 注意:正则末尾绝对不能加 $
    set $spa_fallback 1;
}
if (!-e $request_filename) {
    set $spa_fallback "${spa_fallback}1";
}
if ($spa_fallback = 11) {
    rewrite ^ /index.html last;
}
```

`$spa_fallback` 用拼串模拟「逻辑与」:只有「路径不在排除清单」**且**「磁盘上不存在该文件」两个条件同时成立(结果为 `11`)才回退。nginx 的 `if` 不支持 `&&`,这是标准写法。

> **本次事故(2026-11-04)**:原配置写成 `if ($uri !~ ^/(api/|llms\.txt)$)`。末尾的 `$` 把排除条件锚定成**精确路径 `/api/`**,而真实请求是 `/api/v1/store/apps`,匹配不上 → 被 rewrite 成 `/index.html`。结果 `portal.cenkor.cn/apps` 前端收到 HTML 首页当 JSON 解析,页面统计全是 0,而 nginx 里 `location /api/` 反代明明配得好好的。**去掉 `$` 改前缀匹配**即恢复。

### 4.3 admin 站版(排除项最多)

```nginx
# /www/server/panel/vhost/rewrite/admin.cenkor.cn.conf
# ⚠️ 不要写 location /,否则会与主配置 duplicate location "/"
# 只用 if + rewrite 做 SPA 回退
#
# 必须排除的路径(否则会被下面的 !-e 判为「文件不存在」而 rewrite 成 index.html):
#   /api/                     后端接口
#   /.app-assets/             应用插件静态资源(反代到后端)
#   /landing                  品牌官网(独立静态站,走 server 里的 location ^~ /landing/)
#   /robots.txt /sitemap.xml  独立文本文件,由主配置的 location = 精确匹配提供

set $spa_fallback 0;
if ($uri !~ ^/api/) {
    set $spa_fallback 1;
}
if ($uri ~ ^/\.app-assets/) {
    set $spa_fallback 0;
}
if ($uri ~ ^/landing) {
    set $spa_fallback 0;
}
if ($uri ~ ^/(robots\.txt|sitemap\.xml)$) {
    set $spa_fallback 0;
}
if (!-e $request_filename) {
    set $spa_fallback "${spa_fallback}1";
}
if ($spa_fallback = 11) {
    rewrite ^ /index.html last;
}
```

主 vhost 里对应的精确 location 也一并列在这里,便于核对排除项:

```nginx
location = /robots.txt {
    alias /www/wwwroot/cenkor-admin/frontend/landing/robots.txt;
    default_type text/plain;
    expires -1;
}
location = /sitemap.xml {
    alias /www/wwwroot/cenkor-admin/frontend/landing/sitemap.xml;
    default_type application/xml;
    expires -1;
}
```

> 缺这两段时请求会被下方 `location /` 兜成 SPA 外壳 HTML,爬虫拿到 `text/html` 解析失败,robots 规则等于没生效。

### 4.4 dev 站版(最简)

```nginx
# /www/server/panel/vhost/rewrite/dev.cenkor.cn.conf
set $spa_fallback 0;
if ($uri !~ ^/api/) {
    set $spa_fallback 1;
}
if (!-e $request_filename) {
    set $spa_fallback "${spa_fallback}1";
}
if ($spa_fallback = 11) {
    rewrite ^ /index.html last;
}
```

dev 站主 vhost 里还有两条**业务级 server rewrite**,同样必须在 location 之前:

```nginx
# 应用商店已收归用户端应用中心(portal.cenkor.cn/apps),旧链接 301 过去。
# 必须用 server 级 rewrite:SPA 回退的 rewrite 在 location 匹配之前执行,location 拦不住。
rewrite ^/store/?$ https://portal.cenkor.cn/apps permanent;
rewrite ^/store/(.*)$ https://portal.cenkor.cn/apps permanent;
```

### 4.5 不需要伪静态的站

- `www.cenkor.cn`:`rewrite/www.cenkor.cn.conf` **为空**,靠 `try_files ... @cms_dynamic`(见 §3.5)。
- `docs.user.023ent.net`:`rewrite/docs.user.023ent.net.conf` **为空**,靠 `location / { try_files $uri $uri.html $uri/index.html =404; }`。

给纯静态 / 动态渲染站套 SPA 回退模板,反而会把真实 404 变成 200 首页。

### 4.6 排除清单同步检查表

新增任何一个 `location` 反代或精确静态文件时,回头检查伪静态排除项:

| 主 vhost 新增 | 伪静态必须同步 |
|---|---|
| `location /api/xxx/` | 已被 `^/api/` 覆盖,无需改 |
| `location = /llms.txt`、`= /sitemap.xml` | 加进第一条排除正则,或补一条 `if ($uri ~ ...) set $spa_fallback 0;` |
| `location ^~ /landing/` | 加 `if ($uri ~ ^/landing)` |
| `location /xxx-assets/` | 加对应前缀排除 |
| 新独立静态子站 | `^~` 优先 + 排除,两个都要 |

---

## 5. 配置落点与加载顺序

| 落点 | 路径 | 谁在写 |
|---|---|---|
| 站点主配置 | `/www/server/panel/vhost/nginx/<域名>.conf` | 手工 + 宝塔建站 |
| 宝塔「反向代理」 | `/www/server/panel/vhost/nginx/proxy/<域名>/*.conf` | 面板(dev 站用) |
| 宝塔「伪静态」 | `/www/server/panel/vhost/rewrite/<域名>.conf` | 面板 + 手工 |
| 面板扩展片段 | `/www/server/panel/vhost/nginx/extension/<域名>/*.conf` | 面板(访问日志等) |
| 全局 map | `/www/server/panel/vhost/nginx/0.websocket.conf` | 手工 |

主配置末尾的 include 位置(以 portal 为例):

```nginx
#PHP-INFO-START
location /api/ { ... }
# include /www/server/panel/vhost/nginx/proxy/portal.cenkor.cn/*.conf;
#PHP-INFO-END

#REWRITE-START URL重写规则引用,修改后将导致面板设置的伪静态规则失效
include /www/server/panel/vhost/rewrite/portal.cenkor.cn.conf;
#REWRITE-END
```

**执行顺序**:server 级 `if` / `rewrite`(含 include 进来的伪静态) → `location` 匹配 → `try_files` / `proxy_pass`。所以「伪静态先跑」这条永远成立,`location` 优先级再高也救不回被 rewrite 掉的请求。

---

## 6. 变更 SOP

```bash
F=/www/server/panel/vhost/rewrite/portal.cenkor.cn.conf

# 1) 备份(带时间戳,别用 .bak 覆盖掉上一次的备份)
cp "$F" "${F}.bak-$(date +%Y%m%d-%H%M%S)"

# 2) 修改(建议用脚本精确替换,避免整文件重写丢注释)
python3 - <<'EOF'
p = '/www/server/panel/vhost/rewrite/portal.cenkor.cn.conf'
s = open(p, encoding='utf-8').read()
old = r'^/(api/|llms\.txt)$'
new = r'^/(api/|llms\.txt)'
assert s.count(old) == 1, f'match count = {s.count(old)}'
open(p, 'w', encoding='utf-8').write(s.replace(old, new))
print('patched')
EOF

# 3) 语法检查 —— 不通过绝对不要 reload
nginx -t

# 4) 平滑重载
nginx -s reload

# 5) 验证(见 §7),异常立刻回滚
cp "${F}.bak-20261104-213939" "$F" && nginx -t && nginx -s reload
```

> **改 nginx 不用重启后端 Python 项目。** 后端只在改 `.env` 或 Python 代码时才需要重启;按服务器约定,后端一律由宝塔 Python 项目管理器托管,先 kill 占端口的残留进程释放端口,**不手动拉起**,等宝塔自愈接管。

---

## 7. 验证清单

在服务器上直接跑,每一项都要对得上:

```bash
# API 必须返回 JSON,不能是 text/html
curl -sS -o /dev/null -w '%{http_code} %{content_type}\n' \
  'https://portal.cenkor.cn/api/v1/store/apps?page=1&page_size=12'
# 期望:200 application/json

# 未带 token 的接口要返回结构化 401,而不是 SPA 首页
curl -sS -o /dev/null -w '%{http_code} %{content_type}\n' \
  'https://portal.cenkor.cn/api/v1/auth/me'
# 期望:401 application/json

# SPA 路由仍回退到前端
curl -sS -o /dev/null -w '%{http_code} %{content_type}\n' 'https://portal.cenkor.cn/apps'
# 期望:200 text/html

# 动态文本走后端
curl -sS -o /dev/null -w '%{http_code} %{content_type}\n' 'https://portal.cenkor.cn/llms.txt'
# 期望:200 text/plain

# 官网文档中心(预渲染 docs.html)
curl -sS -o /dev/null -w '%{http_code} %{content_type}\n' 'https://admin.cenkor.cn/landing/docs'
# 期望:200 text/html

# 知识库 cleanUrls
curl -sS -o /dev/null -w '%{http_code} %{content_type}\n' \
  'https://docs.user.023ent.net/cenkor-admin/deploy'
# 期望:200 text/html
```

**最容易被骗的一招**:只看 HTTP 200 不够。`/api/` 被 SPA 回退吞掉时也是 200,只是 `content_type` 变成 `text/html`,前端 `res.json()` 才炸。**一定同时看 `content_type`**,并用 `head -c 200` 扫一眼响应体开头是不是 `<!doctype html`。

前端发版后另做一次:

```bash
# index.html 不缓存,新 chunk 能立即被引用
curl -sS 'https://admin.cenkor.cn/' | grep -o 'index-[A-Za-z0-9_-]*\.js'
```

---

## 8. 故障速查

| 现象 | 根因 | 修法 |
|---|---|---|
| 前端接口拿到 HTML 首页、JSON 解析失败、页面统计全 0 | 伪静态排除正则末尾多了 `$`,`/api/xxx` 被 rewrite 成 `/index.html` | 改前缀匹配,见 §4.2 |
| 「官方应用市场返回了非 JSON 内容」 | **不是 nginx 问题**:后端 `.env` 未配 `MARKET_HUB_URL`,回退 `https://portal.cenkor.cn`(纯前端 SPA) | 配 `MARKET_HUB_URL=https://dev.cenkor.cn`,重启后端 |
| API 502 / connection refused | 后端 8002 未起 | 查宝塔 Python 项目日志,释放端口等自愈,不要手动拉起 |
| 新增一个 API 前缀后全站 404 或返回首页 | 只在主 vhost 加了 `location`,伪静态排除清单没同步 | 按 §4.6 补排除项 |
| `/landing/docs` 404 | 缺 `try_files $uri.html` 或没重新预渲染 `docs.html` | 查 §3.6;重跑 landing-web 构建 |
| 改完伪静态过几天又复发 | 宝塔面板「伪静态」页被保存,规则被覆盖回去 | 从备份恢复,或把规则固化进主 vhost 并停用面板伪静态 |
| 前端发版后白屏 / chunk 404 | `index.html` 被缓存,仍引用已删除的旧 chunk | `location = /index.html { expires -1; }` |
| nginx 启动报 `duplicate location "/api/"` | 主 vhost 和 `proxy/*.conf` 同时定义了 `/api/` | 保留一处,注释掉另一处 include |
| nginx 报 `unknown variable "connection_upgrade"` | 用了宝塔反代面板生成的代码,但全局 `0.websocket.conf` 缺失 | 补 map,见 §3.3 |

---

## 9. 相关文档

- [deploy.md](deploy.md) —— 部署方案(权威):架构拓扑、端口台账、五处配置落点、发布与回滚
- [domain_setup.md](domain_setup.md) —— 域名绑定 + SSL
- [baota_static_deploy.md](baota_static_deploy.md) —— 完整宝塔部署流程(交付别的机器用,非本机生产架构)
- [core_platform.md](core_platform.md) —— 核心平台组成与域名规划
- [index.md](index.md) —— 文档索引
