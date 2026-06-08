# 可选扩展 · 官网 CMS 对接

> **不属于核心平台。** 核心仅含 admin-web + portal-web + backend。  
> 本文描述如何把**外部营销站**（独立 HTML 项目）接到 CMS 公开 API。

---

## 适用场景

- 你有一个独立官网目录（如 `/www/wwwroot/website`），不在本 monorepo 内
- 希望在 **admin 后台**改产品/案例/站点配置，**官网**自动展示

本仓库 **cenkor.cn 实例**即此模式；换其他域名/目录同样适用。

---

## 架构

```
admin.example.com          外部官网 www.example.com
      │                            │
      │ 写入 CMS                    │ GET /api/v1/public/site
      ▼                            ▼
              backend :8002
              PostgreSQL
```

官网仍是**纯静态 HTML**，通过 JS 拉公开 API；API 失败时可降级本地 `site-data.js`。

---

## 宝塔配置

| 项 | 值 |
|----|-----|
| 域名 | `www.example.com`（及 apex 跳转） |
| 根目录 | 你的官网静态目录（**非**本仓库 `frontend/`） |
| PHP | 纯静态 |

**配置文件**追加 [`deploy/addons/website/server-snippet-api.conf`](../../deploy/addons/website/server-snippet-api.conf)：

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8002/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

伪静态一般留空，见 [`deploy/addons/website/rewrite.conf`](../../deploy/addons/website/rewrite.conf)。

---

## 官网前端集成

1. 引入 [`deploy/addons/website/cms-bridge.js`](../../deploy/addons/website/cms-bridge.js)（或自写 fetch）
2. 生产域名上请求同域 `/api/v1/public/site`
3. 在 `.env.prod` 的 `CORS_ORIGINS` 中加入官网域名

验证：

```bash
curl -s https://www.example.com/api/v1/public/site | head
```

---

## Docker 自管 nginx

```bash
# 在 docker-compose.prod 基础上叠加官网挂载
docker compose -f docker-compose.prod.yml -f docker-compose.addon-website.yml up -d
```

- 挂载：[`docker-compose.addon-website.yml`](../../docker-compose.addon-website.yml)
- Nginx 片段：[`deploy/nginx/snippets/website.conf`](../../deploy/nginx/snippets/website.conf)  
  在 `nginx.prod.conf` 中取消注释 `include snippets/website.conf;`

---

## Cenkor 生产实例参考

若部署 cenkor.cn，可在 `.env.prod` 追加：

```bash
# deploy/examples/env.cenkor.snippet
CORS_ORIGINS=https://www.cenkor.cn,https://cenkor.cn,https://admin.cenkor.cn,https://portal.cenkor.cn
```

官网目录：`/www/wwwroot/website`（独立仓库/目录，非本 monorepo 必需文件）。
