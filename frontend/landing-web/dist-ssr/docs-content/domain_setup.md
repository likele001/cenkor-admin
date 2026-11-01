# Cenkor Admin · 域名绑定 + SSL

> 本文只讲**域名解析、宝塔建站、SSL 证书**三件事。
> 端口、路径、依赖服务、验证与排障一律见 [`deploy.md`](deploy.md)，本文不重复。

---

## 现状速查

| 域名 | 站点根目录 | API 反代 | SSL |
|---|---|---|---|
| `admin.cenkor.cn` | `frontend/admin-web/dist` | `/api/` `/api/v1/ws/` `/.app-assets/` → `127.0.0.1:8002` | Let's Encrypt，强制 HTTPS |
| `portal.cenkor.cn` | `frontend/portal-web/dist` | `/api/` → `127.0.0.1:8002` | 同上 |
| `dev.cenkor.cn` | `frontend/developer-web/dist` | ⚠️ **无**（待确认，见 [deploy.md §10.6](deploy.md#106-devcenkercn-无-api-反代)） | 同上 |
| `www.cenkor.cn` | `/www/wwwroot/website`（**外部站，不属本仓库**） | `/api/` → `127.0.0.1:8002` | 同上 |
| `docs.cenkor.cn`<br>`docs.user.023ent.net` | `/www/wwwroot/knowledge/docs/.vitepress/dist` | — | 同上 |

nginx 配置文件：`/www/server/panel/vhost/nginx/<域名>.conf`（宝塔管理，**不在本仓库**）。

---

## Step 1：DNS 解析

在域名注册商控制台加 A 记录，指向本机公网 IP。

| 主机记录 | 类型 | 值 |
|---|---|---|
| `admin` | A | 本机公网 IP |
| `portal` | A | 本机公网 IP |
| `dev` | A | 本机公网 IP |
| `www` | A | 本机公网 IP |

验证：

```bash
for d in admin.cenkor.cn portal.cenkor.cn dev.cenkor.cn www.cenkor.cn; do
  printf '%-22s ' "$d"; dig +short "$d" | head -1
done
```

> ⚠️ 旧版本本文档写的是 `104.152.50.138`，与当前服务器不符，**已改为不写死 IP**。
> 以 `curl -s ifconfig.me` 的实际结果为准。

---

## Step 2：宝塔建站

宝塔面板 → **网站** → **添加站点**。

| 项 | 值 |
|---|---|
| 域名 | 一行一个填 `admin.cenkor.cn`、`portal.cenkor.cn` 等 |
| 根目录 | 按上表填 `frontend/*/dist` 的**绝对路径** |
| PHP 版本 | **纯静态** |
| 数据库 / FTP | **不创建** |

**只反代 `/api/`，不要整站反代 `location /`。** 页面必须走静态 dist，否则 SPA 路由、
静态资源、缓存全部由后端处理，性能和正确性都会出问题。

参考片段：

- `deploy/baota/server-snippet-admin-api.conf`
- `deploy/baota/server-snippet-portal-api.conf`
- `deploy/baota/rewrite-admin.conf` · `rewrite-portal.conf`（SPA 伪静态）

---

## Step 3：SSL 证书

站点设置 → **SSL** → **Let's Encrypt** → 勾选全部域名 → 申请 → 开启**强制 HTTPS**。

- 续期：宝塔自动处理（90 天周期）。
- 若用 Docker 自管 nginx，需自己 `certbot renew` —— **本机不采用此路径**。

---

## Step 4：验证

```bash
for d in admin portal dev www; do
  printf '%-24s ' "https://$d.cenkor.cn/api/health"
  curl -s -o /dev/null -w '%{http_code}\n' --max-time 8 "https://$d.cenkor.cn/api/health"
done
```

期望四个都是 `200`（`dev` 见 [deploy.md §10.6](deploy.md#106-devcenkercn-无-api-反代)）。

更完整的验证清单见 [deploy.md §7](deploy.md#7-验证清单)。

---

## 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 打开域名显示 404 | 根目录填错（漏了 `/dist`），或站点未绑定该域名 |
| 页面能开但接口 404 | 缺 `/api/` 反代片段；确认 `proxy_pass` 指向 `127.0.0.1:8002` |
| 接口 502 | 后端进程没起来，或端口不是 8002；见 [deploy.md §10](deploy.md#10-排障手册) |
| 刷新子路由 404 | 缺 SPA 伪静态（`rewrite-*.conf`） |
| 样式错乱 / 资源 404 | 前端构建时 `VITE_API_BASE_URL` 或 `base` 配错，需重新构建 dist |
| 证书申请失败 | 域名解析未生效，或 80 端口被占用（宝塔需能访问 `/.well-known/`） |

> ⚠️ **不要把 `nginx.prod.conf` 用在宝塔环境里。**
> 它监听 `80/443`，与宝塔 nginx 冲突，会导致必须 `systemctl stop nginx` 才能启动。
> 本机生产走的是「宝塔 nginx + dist 静态 + `/api/` 反代」，不使用 Docker 内 nginx。
