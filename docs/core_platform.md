# Cenkor Admin · 核心平台（不含官网）

本仓库的**可独立部署产品**，由以下部分组成，**不依赖**任何外部营销站或 `/www/wwwroot/website`。

> **部署本平台请直接看 [`deploy.md`](deploy.md)** —— 那是唯一的权威部署文档。
> 本文只讲「这个平台由什么组成、域名怎么规划、与 lightmes 的对应关系」。

---

## 一、组成

```
cenkor-admin/
├── backend/                  FastAPI + SQLAlchemy + Celery
│   └── src/cenkor_admin/     应用代码（PYTHONPATH=src）
│       ├── core/             配置 / 数据库 / 存储 / 安全
│       ├── apps/             内置应用（cms / cloud_storage / commerce / workflow …）
│       └── api/              路由（v1 自动注册 apps/*/router.py）
├── frontend/
│   ├── admin-web/            管理后台（CMS / RBAC / 应用中心 / 审计）
│   ├── portal-web/           用户中心（注册 / 登录 / 资料）
│   ├── developer-web/        开发者门户（开发文档 / 提交应用）
│   ├── landing-web/          落地页（挂在 admin.cenkor.cn/landing/）
│   └── design-tokens/        设计变量（CSS exports，无需构建）
├── deploy/
│   ├── baota/                宝塔：伪静态 / API 片段 / 宿主机 env 模板
│   ├── nginx/                Docker 自管 nginx（本机未采用）
│   ├── systemd/              裸机 systemd 单元（本机未采用）
│   └── examples/             env 模板片段
├── scripts/                  构建 / 部署 / 备份 / 发版
├── docs/                     本文档目录
└── docker-compose*.yml       Docker 可选路径（交付用）
```

| 模块 | 说明 |
|------|------|
| **backend** | REST API、JWT 鉴权、RBAC、CMS 内容管理、应用中心、审计、计费 |
| **admin-web** | 运营后台 SPA |
| **portal-web** | 终端用户 SPA |
| **developer-web** | 开发者门户 SPA |
| **中间件** | PostgreSQL 16、Redis 7、MinIO —— **宿主机原生服务**，非容器 |
| **对象存储** | 主存储为云端七牛云 Kodo，本地 MinIO 作双写备份 |

CMS 模块含**公开只读 API**（`/api/v1/public/*`），供任意前端消费；
**不要求**本仓库内必须有官网项目。

---

## 二、域名规划

本机生产的实际域名（新环境部署时按此结构替换根域名）：

| 站点 | 域名 | 根目录 / 反代 |
|------|------|----------------|
| 管理后台 | `admin.cenkor.cn` | `frontend/admin-web/dist` + `/api/` → 后端 |
| 用户中心 | `portal.cenkor.cn` | `frontend/portal-web/dist` + `/api/` → 后端 |
| 开发者门户 | `dev.cenkor.cn` | `frontend/developer-web/dist`（**API 反代待确认**） |
| 落地页 | `admin.cenkor.cn/landing/` | `frontend/landing-web/dist` |
| 官网 | `www.cenkor.cn` | `/www/wwwroot/website`（**外部站，不属本仓库**），仅反代 `/api/` |

**推荐做法：同域 `/api/` 反代**（宝塔静态模式），前端与 API 同源，**无需 CORS**。

若用独立 API 域，需同时处理 CORS 与跨域 Cookie，复杂度显著上升：

```bash
VITE_API_BASE_URL=https://api.example.com bash scripts/build-frontends.sh
```

> ⚠️ `deploy/examples/env.cenkor.snippet` 里建议的 `api.cenkor.cn` **实际不存在**
> （没有对应 nginx vhost），不要照着配。

---

## 三、快速开发（本地开发机）

> 仅用于开发者本机。**生产环境不用 Docker**，见 [`deploy.md`](deploy.md)。

```bash
cp .env.example .env
docker compose up -d                  # 起 PG / Redis / MinIO / backend / admin-web dev
docker compose exec backend alembic upgrade head
docker compose exec backend python -m cenkor_admin.scripts.seed
```

- 管理后台：<http://localhost:5173>
- 用户中心：`npm run dev:portal` → <http://localhost:5175>
- API 文档：<http://localhost:8000/api/docs>
- 默认账号：`admin@cenkor.cn` / `admin123`

> 后端 lifespan 会自动执行 `alembic upgrade head`，通常无需手动跑迁移。

> ⚠️ **安全提示**：默认管理员密码是明文写在文档里的种子数据。
> **任何部署到公网之前必须先做三件事**：① 改默认管理员密码；② 换 `SECRET_KEY`；
> ③ 删除或禁用不需要的种子账号。否则任何人都能用 `admin@cenkor.cn` / `admin123` 登录。

---

## 四、生产部署

**本机生产 = 宿主机 + 宝塔，不使用 Docker。**

完整流程、端口台账、配置优先级、验证清单、回滚与排障，全部在
[**`deploy.md`**](deploy.md) —— 请以它为准，本文不重复。

速览：

| 组件 | 位置 | 端口 |
|---|---|---|
| 后端 | 宝塔 Python 项目 `cenkor`，用户 `www` | `8002` |
| PostgreSQL | 宿主机原生 | `5432` |
| Redis | 宿主机原生 | `6379 / db5` |
| MinIO | 宿主机原生（systemd） | `9000` |
| 前端 | 宝塔 nginx 直接 serve `dist` | — |

**其他部署模式**（本机未采用，仅供交付或换环境）：

| 模式 | 命令 | 文档 |
|------|------|------|
| Docker 全栈（交付演示） | `bash scripts/deploy.sh --mode docker` | [`fullstack_deploy.md`](fullstack_deploy.md) |
| 裸机 systemd | `sudo bash scripts/install-native.sh` | [`native_deploy.md`](native_deploy.md) |
| 宝塔 + Docker 混合（历史） | — | [`baota_static_deploy.md`](baota_static_deploy.md) |

在 `.env.prod` 中把 `admin.example.com`、`portal.example.com` 换成你的真实域名。

---

## 五、宝塔建站要点

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

**原则：** 页面走 `dist`，**只**反代 `/api/` 到 `127.0.0.1:8002`，**禁止**整站 `/` 反代后端。

---

## 六、可选扩展

| 扩展 | 说明 | 文档 |
|------|------|------|
| 官网 CMS 对接 | 外部静态站读 `/api/v1/public/site` | [`addons/website_cms.md`](addons/website_cms.md) |
| 打包交付 | 核心平台压缩包 | [`packaging.md`](packaging.md) |
| 独立 API 子域 | `api.example.com` | [`deploy/baota/nginx-api.example.conf`](../deploy/baota/nginx-api.example.conf) |

扩展配置均在 [`deploy/addons/`](../deploy/addons/)，与核心部署解耦。

---

## 七、与 lightmes 对照

| lightmes | 本仓库（核心） |
|----------|----------------|
| `frontend-admin-pro/dist` | `frontend/admin-web/dist` |
| `frontend-portal/dist` | `frontend/portal-web/dist` |
| `admin.xxx.net` | `admin.cenkor.cn` |
| `register.xxx.net` | `portal.cenkor.cn` |
| 后端 `127.0.0.1:8000`（宿主机） | 后端 `127.0.0.1:8002`（宿主机） |

> lightmes 与本平台在本机是**同构**的：都是宿主机进程 + 宝塔 nginx + 宿主 PG/Redis。
> 注意 **lightmes 占 `8000`**，本平台占 `8002`，不要混。

---

打包与发版记录见 [`packaging.md`](packaging.md)、[`release/changelog.md`](release/changelog.md)。
