# 打包与交付

本文档描述如何将 **Cenkor Admin 核心平台**打成可交付压缩包，以及接收方如何解压部署。

> 核心平台 = `backend` + `admin-web` + `portal-web` + 部署脚本与文档。  
> **不含**外部官网（`www.cenkor.cn` / `/www/wwwroot/website`），官网见 [addons/WEBSITE_CMS.md](addons/WEBSITE_CMS.md)。

---

## 一、产物类型

| 类型 | 文件名模式 | 说明 |
|------|------------|------|
| **核心包** | `cenkor-admin-core-<version>-<date>.tar.gz` | 可独立部署的完整核心平台 |
| 官网扩展 | 见 `deploy/addons/website/` | 不单独打大包，按需复制配置 |

当前版本号：`0.1.0`（可通过环境变量 `PACKAGE_VERSION` 覆盖）

---

## 二、打包命令

在仓库根目录执行：

```bash
# 重新构建前端 + 打包（推荐发版前）
bash scripts/package-core.sh

# 使用已有 dist，快速打包
bash scripts/package-core.sh --skip-build

# 指定版本号
PACKAGE_VERSION=0.2.0 bash scripts/package-core.sh
```

或使用 npm：

```bash
npm run package:core
```

**产出路径：**

```
release/cenkor-admin-core-0.1.0-YYYYMMDD.tar.gz
```

压缩包内根目录同名，并附带 `PACKAGE.md` 快速安装说明。

---

## 三、包内清单

### 包含

| 路径 | 说明 |
|------|------|
| `backend/` | FastAPI 源码、Alembic 迁移、`pyproject.toml` |
| `frontend/admin-web/dist/` | 管理后台**已构建**静态文件 |
| `frontend/admin-web/src/` | 管理后台源码（便于二次开发） |
| `frontend/portal-web/dist/` | 用户中心**已构建**静态文件 |
| `frontend/portal-web/src/` | 用户中心源码 |
| `frontend/design-tokens/` | 设计 token |
| `deploy/baota/` | 宝塔伪静态、API 反代片段 |
| `deploy/nginx/` | Docker 自管 nginx 配置 |
| `deploy/systemd/` | 裸机 systemd 单元 |
| `scripts/` | 构建、部署、备份、打包脚本 |
| `docs/CORE_PLATFORM.md` | 核心平台文档 |
| `docs/BAOTA_STATIC_DEPLOY.md` | 宝塔部署文档 |
| `docs/NATIVE_DEPLOY.md` | 裸机部署文档 |
| `docs/PACKAGING.md` | 本文档 |
| `docs/INDEX.md` | 文档索引 |
| `docker-compose.yml` | 开发环境 |
| `docker-compose.prod.yml` | 生产 Docker |
| `docker-compose.baota-static.yml` | 宝塔静态模式后端栈 |
| `docker-compose.baota.yml` | 宝塔反代 Docker 前端 |
| `.env.example` | 开发环境变量模板 |
| `PACKAGE.md` | 包内安装速查 |

### 不包含（需目标环境自行准备）

| 项 | 原因 |
|----|------|
| `node_modules/` | 体积大；生产只需 `dist` |
| `.env` / `.env.prod` | 含密钥，接收方自行 `gen-secrets.sh` 生成 |
| `.git/` | 非必需 |
| `deploy/addons/` | 官网等可选扩展，与核心解耦 |
| `docs/addons/` | 同上 |
| `docs/DOMAIN_SETUP.md` | Cenkor 实例专用域名文档 |

---

## 四、接收方部署流程

### 4.1 解压

```bash
tar -xzf cenkor-admin-core-0.1.0-20260607.tar.gz
cd cenkor-admin-core-0.1.0-20260607
```

### 4.2 生成生产配置

```bash
bash scripts/gen-secrets.sh
```

编辑 `.env.prod`，至少修改：

```bash
# 改成你的域名
CORS_ORIGINS=https://admin.your.com,https://portal.your.com
FEISHU_REDIRECT_URI=https://admin.your.com/auth/feishu/callback

# 同域反代 /api/ 时留空；独立 API 子域则填写
VITE_API_BASE_URL=
PUBLIC_BASE_URL=
```

Cenkor 生产实例可参考仓库内 `deploy/examples/env.cenkor.snippet`（**不在核心包内**）。

### 4.3 启动后端

```bash
bash scripts/deploy-baota-static.sh
```

或手动：

```bash
docker compose -f docker-compose.baota-static.yml --env-file .env.prod up -d
docker compose -f docker-compose.baota-static.yml exec -T backend alembic upgrade head
docker compose -f docker-compose.baota-static.yml exec -T backend python -m cenkor_admin.scripts.seed
```

### 4.4 宝塔建站（2 个站点）

| 站点 | 根目录 | 伪静态 | API 片段 |
|------|--------|--------|----------|
| 管理后台 | `frontend/admin-web/dist` | `deploy/baota/rewrite-admin.conf` | `deploy/baota/server-snippet-admin-api.conf` |
| 用户中心 | `frontend/portal-web/dist` | `deploy/baota/rewrite-portal.conf` | `deploy/baota/server-snippet-portal-api.conf` |

详细步骤：[BAOTA_STATIC_DEPLOY.md](BAOTA_STATIC_DEPLOY.md)

### 4.5 验证

```bash
curl -s http://127.0.0.1:8002/api/health
curl -sI https://admin.your.com/
curl -sI https://portal.your.com/
curl -s https://admin.your.com/api/health
```

默认账号：`admin@cenkor.cn` / `admin123`（首次 seed 后请改密）

---

## 五、环境变量

| 变量 | 开发 | 生产 | 说明 |
|------|------|------|------|
| `CORS_ORIGINS` | localhost | 必填 | admin + portal 域名，逗号分隔 |
| `VITE_API_BASE_URL` | 空 | 通常空 | 构建前端时注入；同域反代留空 |
| `BACKEND_HOST_PORT` | — | `8002` | 宿主机后端端口 |
| `DATABASE_URL` | docker | docker/本机 | PostgreSQL 连接串 |

完整模板见 `.env.example`（开发）与 `scripts/gen-secrets.sh` 生成的 `.env.prod`。

---

## 六、二次开发与重新打包

若接收方修改了前端源码：

```bash
npm install          # 根目录 workspace
bash scripts/build-frontends.sh
bash scripts/package-core.sh --skip-build
```

若只改后端：

```bash
docker compose -f docker-compose.baota-static.yml --env-file .env.prod up -d --build backend
```

---

## 七、发布记录

每次发版建议在 [release/CHANGELOG.md](release/CHANGELOG.md) 追加条目，并保留 `release/` 目录下的压缩包副本（该目录已 gitignore，仅作本地/服务器存储）。

---

## 八、与官网的关系

| 组件 | 是否在核心包 | 说明 |
|------|--------------|------|
| CMS 后台（admin） | ✅ | 编辑产品、案例、站点配置 |
| 公开 API `/api/v1/public/*` | ✅ | 后端自带，任意前端可调用 |
| 外部营销站 HTML | ❌ | 独立项目，见 [addons/WEBSITE_CMS.md](addons/WEBSITE_CMS.md) |

核心包可**单独交付**；需要官网 CMS 时再提供 addon 配置或 Cenkor 实例的 `website` 目录。
