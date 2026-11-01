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

### 3.1 包含

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

### 3.2 不包含（需目标环境自行准备）

| 项 | 原因 |
|----|------|
| `node_modules/` | 体积大；生产只需 `dist` |
| `.env` **及所有 `.env.*`**（`.env.prod` / `.env.bak-*` / `.env.local`） | 含密钥；只保留 `.env.example` 模板 |
| `*.bak` / `*.bak-*` / `*.bak.*` / `_bak-*` / `_rollback_bak_*` | 本地备份目录与旧产物 |
| `*.log` / `logs/`（含 `backend/logs/`） | 生产日志，单份可达 5 MB+，且含访问 IP |
| `.stale-apps/`（`backend/.stale-apps/`） | 已卸载应用的残留，含闭源 payment 产物 |
| `_rollback_bak_*/cenkor_db.sql` 等库备份 | 全量业务数据，单份 1.7 MB+ |
| `.mimocode/`、`./www`（嵌套误建目录） | 工具元数据、历史误操作残留 |
| `.git/` | 非必需 |
| `deploy/addons/` / `docs/addons/` / `deploy/examples/` | 官网等可选扩展，与核心解耦 |
| `docs/domain_setup.md` | Cenkor 实例专用域名文档 |
| **`backend/src/cenkor_admin/apps/{erp,crm,mes,workflow,payment}/`** | **闭源商业应用**，见下方 ⚠️ |
| **`backend/src/apps/`**（外置应用：payment / commerce） | **闭源商业源码** |
| **`backend/src/cenkor_admin/static/apps/{erp,crm,mes,workflow,payment}/`** | 上述应用的前端插件产物 |
| **`backend/alembic/versions/{erp,crm,mes}/`** | 上述应用的迁移 |
| **`frontend/developer-web/`** | 开发者门户，闭源商业资产 |
| `verify_v11.py` | MES 端到端验证脚本，属闭源模块 |

> ⚠️ **闭源资产排除是硬要求，不是可选项。**
>
> 闭源应用在这台服务器上是**物理存在**的（erp 64 个 .py、crm 21、mes 24、workflow 8），
> 它们只靠 `.gitignore` 阻止进 git。而 `package-core.sh` 用的是 **`tar`**——
> **tar 读文件系统，不读 `.gitignore`**。漏一条 `--exclude`，整份 ERP/CRM/MES 源码
> 就会跟着核心包发到客户手里。
>
> 同样的机制还会带走**从来没进过 git 的东西**：`.env.bak-20261007`（带真实密钥）、
> `backend/logs/hub.log`（5 MB 生产日志）、`_rollback_bak_20261014/cenkor_db.sql`
> （1.7 MB 全库备份）、`backend/.stale-apps/`（含闭源 payment 残留）。
> 这些在 2026-11-01 的一次打包里全部出现过，包体积从 3.8 MB 虚涨到 13 MB。
>
> 因此脚本现在有**五道防线**，任何一道不通过都**删掉产物并 `exit 1`**：
>
> | 自检 | 拦什么 | 输出 |
> |------|--------|------|
> | 闭源资产 | erp / crm / mes / workflow / payment / src-apps / developer-web / verify_v11.py | `自检通过：包内无闭源资产…` |
> | 凭据文件 | 任何 `.env` 变体（example 除外）、`*.pem`、`*.key`、`id_rsa*`、`*.bak*` | `自检通过：包内无凭据 / 备份文件…` |
> | 运行时垃圾 | `logs/`、`*.log`、`_bak-*`、`_rollback_bak_*`、`.bak.`、`.stale-apps/`、`www/wwwroot/` | `自检通过：包内无运行时垃圾…` |
> | 关键文件在不在 | 后端入口、`alembic.ini`、三套前端 `index.html`、`.env.example`、`PACKAGE.md` | `自检通过：关键文件齐全…` |
> | 迁移链自洽 | 每个 `down_revision` 都能在包内找到 | `自检通过：包内迁移链自洽…` |
>
> 最后一道是**正向**检查——防止 `--exclude` 写过头把包打空（包能打出来但缺 dist，
> 用户部署完是个白屏）。前四道是**反向**检查，防止脏东西出去。
>
> 新增一个商业应用时，**必须同时**更新 `--exclude`、`FORBIDDEN_PATTERNS`，
> 以及上面「不包含」表，否则自检会拦下你——这正是它存在的意义。

### 3.3 迁移链为什么要重接

核心包排除了 `alembic/versions/{erp,crm,mes}/`，但迁移是**一条串行链**：

```
crm_0006 → mes_0001 → … → mes_0009 → 20260922_0020_commerce → …
```

`commerce/20260922_0020_commerce.py` 原本 `down_revision = "20260904_mes_0009"`。
闭源段被整段排除后，这个父节点在包内不存在，`alembic upgrade head` 直接报
`KeyError: '20260904_mes_0009'`——包能正常解压，但**迁移跑不起来**。

该迁移只新建 `app_pricing` / `app_orders` / `app_licenses` / `app_license_bindings`
四张自建表，**不引用 MES/ERP/CRM 的任何表或 schema**，所以脚本在打包时把这个父节点
置空（只改包内副本，不动仓库源码）：

```
▸ 已重接 commerce 迁移父节点（原 20260904_mes_0009 属闭源段，无表依赖）
```

交付包实测：

```bash
cd backend && alembic heads
# 20261020_0035_app_publish (head)
# 20261027_0100_app_schema (head)
```

> **升级路径注意**：核心包与完整仓库的迁移历史在这一处不同。以后接入商业模块时，
> 用完整仓库的迁移目录，不要把两套迁移目录混用。

> **交付前自检**（对已有的包也适用）：
>
> ```bash
> P=release/cenkor-admin-core-<version>-<date>.tar.gz
> # ① 闭源资产 / 凭据 / 垃圾，输出应为空
> tar -tzf "$P" | grep -E 'backend/src/apps/|apps/(erp|crm|mes|workflow|payment)/|frontend/developer-web/|\.env\.|\.log$|\.stale-apps/|_bak' | head
> # ② 迁移链能不能跑
> tar -xzf "$P" -C /tmp && (cd /tmp/$(basename "$P" .tar.gz)/backend && alembic heads)
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
> 重新打包后同样会跑 §3.2 里的五道自检。如果接收方后来自己加了商业应用，
> 打包会被自检拦下——按提示更新 `--exclude` 与 `FORBIDDEN_PATTERNS` 即可。
> 若自检报「迁移链不完整」，说明新加的迁移接在了不存在的父节点后面，参照 §3.3 补重接逻辑。

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
