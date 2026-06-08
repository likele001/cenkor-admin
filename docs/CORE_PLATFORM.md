# Cenkor Admin · 核心平台（不含官网）

本仓库的**可独立部署产品**由以下部分组成，**不依赖**任何外部营销站或 `/www/wwwroot/website`。

---

## 一、组成

```
cenkor-admin/
├── backend/              FastAPI + SQLAlchemy + Celery
├── frontend/
│   ├── admin-web/        管理后台（CMS / RBAC / 应用中心 / 审计）
│   └── portal-web/       用户中心（注册 / 登录 / 资料）
├── deploy/
│   ├── baota/            宝塔：admin + portal 伪静态 / API 片段
│   ├── nginx/            Docker 自管 nginx（admin + 可选 api 子域）
│   └── systemd/          裸机 systemd 单元
├── scripts/              构建、部署、备份
└── docker-compose*.yml
```

| 模块 | 说明 |
|------|------|
| **backend** | REST API、JWT 鉴权、RBAC、CMS 内容管理、应用中心、审计 |
| **admin-web** | 运营后台 SPA |
| **portal-web** | 终端用户 SPA |
| **中间件** | PostgreSQL 16、Redis 7、MinIO（对象存储） |

CMS 模块含**公开只读 API**（`/api/v1/public/*`），供任意前端消费；**不要求**本仓库内必须有官网项目。

---

## 二、域名规划（最小集）

| 站点 | 示例域名 | 根目录 / 反代 |
|------|----------|----------------|
| 管理后台 | `admin.example.com` | `frontend/admin-web/dist` + `/api/` → 后端 |
| 用户中心 | `portal.example.com` | `frontend/portal-web/dist` + `/api/` → 后端 |
| API 子域（可选） | `api.example.com` | 整站反代 → 后端 |

构建时若使用独立 API 域：

```bash
VITE_API_BASE_URL=https://api.example.com bash scripts/build-frontends.sh
```

留空则各前端站点**同域** `/api/` 反代（宝塔静态模式推荐）。

---

## 三、快速开发

```bash
cp .env.example .env
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec backend python -m cenkor_admin.scripts.seed
```

- 管理后台：http://localhost:5173  
- 用户中心：`npm run dev:portal` → http://localhost:5175  
- API 文档：http://localhost:8000/api/docs  
- 默认账号：`admin@cenkor.cn` / `admin123`（seed 可改）

---

## 四、生产部署

| 模式 | 命令 | 文档 |
|------|------|------|
| **宝塔静态 dist（推荐）** | `bash scripts/deploy.sh --mode baota-static` | [`BAOTA_STATIC_DEPLOY.md`](BAOTA_STATIC_DEPLOY.md) |
| Docker 自管 | `bash scripts/deploy.sh --mode docker` | [`docker-compose.prod.yml`](../docker-compose.prod.yml) |
| 宝塔反代 Docker 前端 | `bash scripts/deploy.sh --mode baota` | [`DOMAIN_SETUP.md`](DOMAIN_SETUP.md) |
| 裸机 systemd | `sudo bash scripts/install-native.sh` | [`NATIVE_DEPLOY.md`](NATIVE_DEPLOY.md) |

首次生产：

```bash
bash scripts/gen-secrets.sh    # 生成 .env.prod（通用域名占位符）
bash scripts/deploy-baota-static.sh
```

在 `.env.prod` 中把 `admin.example.com`、`portal.example.com` 换成你的真实域名。

---

## 五、宝塔核心建站（2 个站点）

### admin

| 项 | 值 |
|----|-----|
| 根目录 | `…/cenkor-admin/frontend/admin-web/dist` |
| 伪静态 | [`deploy/baota/rewrite-admin.conf`](../deploy/baota/rewrite-admin.conf) |
| API | [`deploy/baota/server-snippet-admin-api.conf`](../deploy/baota/server-snippet-admin-api.conf) |

### portal

| 项 | 值 |
|----|-----|
| 根目录 | `…/cenkor-admin/frontend/portal-web/dist` |
| 伪静态 | [`deploy/baota/rewrite-portal.conf`](../deploy/baota/rewrite-portal.conf) |
| API | [`deploy/baota/server-snippet-portal-api.conf`](../deploy/baota/server-snippet-portal-api.conf) |

**原则：** 页面走 `dist`，**只**反代 `/api/` 到 `127.0.0.1:8002`，禁止整站 `/` 反代后端。

---

## 六、可选扩展

| 扩展 | 说明 | 文档 |
|------|------|------|
| 官网 CMS 对接 | 外部静态站读 `/api/v1/public/site` | [`addons/WEBSITE_CMS.md`](addons/WEBSITE_CMS.md) |
| 打包交付 | 核心平台压缩包 | [`PACKAGING.md`](PACKAGING.md) |
| 独立 API 子域 | `api.example.com` | [`deploy/baota/nginx-api.example.conf`](../deploy/baota/nginx-api.example.conf) |

扩展配置均在 [`deploy/addons/`](../deploy/addons/)，与核心部署解耦。

---

## 七、与 lightmes 对照

| lightmes | 本仓库（核心） |
|----------|----------------|
| `frontend-admin-pro/dist` | `frontend/admin-web/dist` |
| `frontend-portal/dist` | `frontend/portal-web/dist` |
| `admin.xxx.net` | `admin.example.com` |
| `register.xxx.net` | `portal.example.com` |
| 后端 `127.0.0.1:8000` | `127.0.0.1:8002` |

---

打包与发版记录见 [`docs/PACKAGING.md`](PACKAGING.md)、[`docs/release/CHANGELOG.md`](release/CHANGELOG.md)。
