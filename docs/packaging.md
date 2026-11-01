# 打包与交付

本文档描述如何将 **Cenkor Admin 核心平台**打成可交付压缩包，以及接收方如何解压部署。

> 核心平台 = `backend` + `admin-web` + `portal-web` + 部署脚本与文档。  
> **不含**外部官网（`www.cenkor.cn` / `/www/wwwroot/website`），官网见 [addons/website_cms.md](addons/website_cms.md)。

---

## 一、产物类型

| 类型 | 文件名模式 | 说明 |
|------|------------|------|
| **核心包** | `cenkor-admin-core-<version>-<date>.tar.gz` | 可独立部署的完整核心平台 |
| 官网扩展 | 见 `deploy/addons/website/` | 不单独打大包，按需复制配置 |

版本号取自 `backend/src/cenkor_admin/VERSION`（该文件是唯一来源，`/api/health` 里的 `version`
也是它）；`PACKAGE_VERSION=...` 可临时覆盖。当前值用一条命令确认，别信文档：

```bash
cat backend/src/cenkor_admin/VERSION
```

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
release/cenkor-admin-core-<version>-<YYYYMMDD>.tar.gz
```

压缩包内根目录同名，并附带 `PACKAGE.md` 快速安装说明。

---

## 三、包内清单

### 包含

| 路径 | 说明 |
|------|------|
| `backend/` | FastAPI 源码、**公开链** Alembic 迁移、`pyproject.toml` |
| `frontend/admin-web/dist/` | 管理后台**已构建**静态文件 |
| `frontend/admin-web/src/` | 管理后台源码（便于二次开发） |
| `frontend/portal-web/dist/` | 用户中心**已构建**静态文件 |
| `frontend/portal-web/src/` | 用户中心源码 |
| `frontend/landing-web/` | 品牌落地页（源码 + dist） |
| `frontend/design-tokens/` | 设计 token |
| `backend/src/cenkor_admin/static/apps/` | **开源**应用的插件产物（`cloud_storage` / `my_todo` / `quick_notes`） |
| `deploy/baota/` | 宝塔伪静态、API 反代片段 |
| `deploy/nginx/` | Docker 自管 nginx 配置 |
| `deploy/systemd/` | 裸机 systemd 单元 |
| `scripts/` | 构建、部署、备份、打包脚本 |
| `docs/` | 全部文档（`addons/` 与 `domain_setup.md` 除外） |
| `docker-compose*.yml` | 开发 / 生产 / 宝塔各模式 |
| `.env.example` | 开发环境变量模板 |
| `PACKAGE.md` | 包内安装速查（打包时生成） |

### 不包含（需目标环境自行准备）

| 项 | 原因 |
|----|------|
| `node_modules/` | 体积大；生产只需 `dist` |
| `.env` / `.env.prod` | 含密钥，接收方自行 `gen-secrets.sh` 生成 |
| `.git/` | 非必需 |
| `deploy/addons/` / `docs/addons/` / `deploy/examples/` | 官网等可选扩展，与核心解耦 |
| `docs/domain_setup.md` | Cenkor 实例专用域名文档 |
| **`backend/src/cenkor_admin/apps/{erp,crm,mes,workflow,payment}/`** | **闭源商业应用**，见下方 ⚠️ |
| **`backend/src/apps/`**（外置应用：payment / commerce） | **闭源商业源码** |
| **`backend/src/cenkor_admin/static/apps/{erp,crm,mes,workflow,payment}/`** | 上述应用的前端插件产物 |
| **`backend/alembic/versions/{erp,crm,mes}/`** | 上述应用的迁移 |
| **`frontend/developer-web/`** | 开发者门户，闭源商业资产 |

> ⚠️ **闭源资产排除是硬要求，不是可选项。**
>
> 闭源应用在这台服务器上是**物理存在**的（erp 64 个 .py、crm 21、mes 24、workflow 8），
> 它们只靠 `.gitignore` 阻止进 git。而 `package-core.sh` 用的是 **`tar`**——
> **tar 读文件系统，不读 `.gitignore`**。漏一条 `--exclude`，整份 ERP/CRM/MES 源码
> 就会跟着核心包发到客户手里。
>
> 因此脚本现在有**两道防线**：
>
> 1. `--exclude` 列表显式排除上表所有闭源路径；
> 2. **压缩后自检**（fail-closed）——扫包内文件名，命中任一闭源特征路径就
>    **删掉产物并 `exit 1`**，不允许静默产出：
>
> ```bash
> ▸ 自检通过：包内无闭源资产（erp / crm / mes / workflow / payment / src-apps / developer-web）
> ```
>
> 新增一个商业应用时，**必须同时**更新 `--exclude` 与自检正则
> （`FORBIDDEN_PATTERNS`），否则自检会拦下你——这正是它存在的意义。
>
> **交付前自检**（对已有的包也适用）：
>
> ```bash
> tar -tzf release/cenkor-admin-core-*.tar.gz \
>   | grep -E 'backend/src/apps/|apps/(erp|crm|mes|workflow|payment)/|frontend/developer-web/' \
>   | head
> # 输出为空才安全
> ```

---

## 四、接收方部署流程

### 4.1 解压

```bash
tar -xzf cenkor-admin-core-<version>-<date>.tar.gz
cd cenkor-admin-core-<version>-<date>
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

> 接收方若也用**宝塔宿主机**部署（后端跑在宝塔 Python 项目里），请参考
> [`deploy.md`](deploy.md)；下面的脚本走的是 **Docker 中间件**路径。

```bash
bash scripts/deploy-baota-static.sh
```

或手动：

```bash
docker compose -f docker-compose.baota-static.yml --env-file .env.prod up -d
docker compose -f docker-compose.baota-static.yml exec -T backend alembic upgrade heads
docker compose -f docker-compose.baota-static.yml exec -T backend python -m cenkor_admin.scripts.seed
```

### 4.4 宝塔建站（2 个站点）

| 站点 | 根目录 | 伪静态 | API 片段 |
|------|--------|--------|----------|
| 管理后台 | `frontend/admin-web/dist` | `deploy/baota/rewrite-admin.conf` | `deploy/baota/server-snippet-admin-api.conf` |
| 用户中心 | `frontend/portal-web/dist` | `deploy/baota/rewrite-portal.conf` | `deploy/baota/server-snippet-portal-api.conf` |

> **只有 2 个站点。** `deploy/baota/` 里还有 `rewrite-developer.conf` /
> `server-snippet-developer-api.conf`，那是 Cenkor 自有实例的开发者门户
> （`dev.cenkor.cn`）用的，**`frontend/developer-web` 不在核心包内**（闭源商业资产），
> 接收方不需要它。

详细步骤：[baota_static_deploy.md](baota_static_deploy.md)

### 4.5 验证

```bash
curl -s http://127.0.0.1:8002/api/health
curl -sI https://admin.your.com/
curl -sI https://portal.your.com/
curl -s https://admin.your.com/api/health
```

管理员：`admin@cenkor.cn`（**无默认口令**，初始口令由 seed 随机生成并只打印一次；忘记可 `bash scripts/reset-admin-password.sh` 重置）

---

## 五、环境变量

| 变量 | 开发 | 生产 | 说明 |
|------|------|------|------|
| `CORS_ORIGINS` | localhost | 必填 | admin + portal 域名，逗号分隔 |
| `VITE_API_BASE_URL` | 空 | 通常空 | 构建前端时注入；同域反代留空 |
| `BACKEND_HOST_PORT` | — | `8002` | 宿主机后端端口 |
| `DATABASE_URL` | docker | 宿主机或容器 | PostgreSQL 连接串（本机生产指向宿主机 `127.0.0.1:5432`） |
| `PACKAGE_VERSION` | — | — | **打包时**临时覆盖版本号；不设则读 `backend/src/cenkor_admin/VERSION` |

完整模板见 `.env.example`（开发）与 `scripts/gen-secrets.sh` 生成的 `.env.prod`。

---

## 六、二次开发与重新打包

若接收方修改了前端源码：

```bash
npm install          # 根目录 workspace
bash scripts/build-frontends.sh
bash scripts/package-core.sh --skip-build
```

> 核心包里没有 `frontend/developer-web`，`build-frontends.sh` 会自动**跳过**它
> （输出「跳过 developer-web（闭源商业资产，未随仓库分发）」），这是正常现象，
> 不是构建失败。
>
> 重新打包后同样会跑闭源资产自检（见 §三）。如果接收方后来自己加了商业应用，
> 打包会被自检拦下——按提示更新 `--exclude` 与 `FORBIDDEN_PATTERNS` 即可。

若只改后端：

```bash
docker compose -f docker-compose.baota-static.yml --env-file .env.prod up -d --build backend
```

---

## 七、发布记录

每次发版建议在 [release/changelog.md](release/changelog.md) 追加条目，并保留 `release/` 目录下的压缩包副本（该目录已 gitignore，仅作本地/服务器存储）。

---

## 八、与官网的关系

| 组件 | 是否在核心包 | 说明 |
|------|--------------|------|
| CMS 后台（admin） | ✅ | 编辑产品、案例、站点配置 |
| 公开 API `/api/v1/public/*` | ✅ | 后端自带，任意前端可调用 |
| 外部营销站 HTML | ❌ | 独立项目，见 [addons/website_cms.md](addons/website_cms.md) |

核心包可**单独交付**；需要官网 CMS 时再提供 addon 配置或 Cenkor 实例的 `website` 目录。
