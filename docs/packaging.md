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
| `frontend/landing/` | 官网线上目录（nginx 直接服务 `admin.cenkor.cn/landing/`）。构建产物**不入 git**，打包时从磁盘收集；只有 6 个不参与构建的旧静态页来自跟踪清单 |
| `frontend/design-tokens/` | 设计 token |
| `backend/src/cenkor_admin/static/apps/` | **开源**应用的插件产物（`cloud_storage` / `my_todo` / `quick_notes`） |
| `deploy/baota/` | 宝塔伪静态、API 反代片段 |
| `deploy/nginx/` | Docker 自管 nginx 配置 |
| `deploy/systemd/` | 裸机 systemd 单元 |
| `scripts/` | 构建、部署、备份、打包脚本 |
| `docs/` | 全部文档（`addons/` 与 `domain_setup.md` 除外） |
| `docs/05-用户手册/` | 9 本使用手册（闭源模块的 crm/erp/mes/workflow 4 本除外；payment 手册自 v0.5.11 起随包交付） |
| `docker-compose*.yml` | 开发 / 生产 / 宝塔各模式 |
| `.env.example` | 开发环境变量模板 |
| `deploy/baota/cenkor-backend.host.env.example` | 生产环境变量模板（真实 `host.env` 不进包） |
| `PACKAGE.md` | 包内安装速查（打包时生成） |

### 3.2 不包含 —— 由 `.gitignore` 决定

**打包不再维护一份长长的 `--exclude` 名单，而是以 `git ls-files` 为文件源。**
凡 `.gitignore` 里登记的东西，`git ls-files` 天然不会输出，也就不会进包：

| 自动排除的内容 | 依据 |
|----------------|------|
| 闭源应用 `apps/{erp,crm,mes,workflow}/`、外置 `backend/src/apps/`（现仅 collect） | `.gitignore` 应用目录规则 |
| 闭源迁移（`versions/{erp,crm,mes}/` 整目录 + ext 混合目录里的 workflow 迁移） | `.gitignore` 逐个登记。commerce 目录自 v0.5.11 起整体开源 |
| `frontend/developer-web/`（开发者门户） | `.gitignore` |
| `deploy/baota/cenkor-backend.host.env`（**真实 SECRET_KEY + 数据库口令**） | `.gitignore:47` |
| `.env` / `.env.*` / `*.env`（只保留 `.env.example` 模板） | `.gitignore` |
| `*.log`、`backend/logs/`、`.stale-apps/`、`node_modules/`、`__pycache__/` | `.gitignore` |
| `*.bak*`、`_bak-*`、`_rollback_bak_*`、`*.orig`、`*.rej` | `.gitignore` |

脚本里只保留**少量「已进 git 但不该交付」的例外**（在 `grep -zvE` 那一行）：

| 例外 | 原因 |
|------|------|
| `frontend/developer-web/` | 防御性：即使有人误提交也不出门 |
| `docs/domain_setup.md` | Cenkor 实例专用域名文档 |
| `deploy/{addons,website,examples,nginx/snippets}/`、`docs/addons/`、`docker-compose.addon-website.yml` | 官网等可选扩展 |
| `verify_v11.py` | MES 端到端验证脚本，属闭源模块 |
| `docs/05-用户手册/{crm,erp,mes,workflow}_操作手册.md` | 闭源模块的使用说明（payment 手册已随包交付） |
| `www/wwwroot/`、`.mimocode/` | 历史误操作残留、IDE 计划文件 |
| `*.bak*`（正则 `\.bak[^/]*$`） | 误提交进 git 的备份文件 |

> ⚠️ **为什么放弃 `--exclude` 黑名单**
>
> 2026-10 到 11 月，同一类事故发生了四次，每次都是「`.gitignore` 里有、`tar` 不知道」：
>
> 1. 闭源应用目录整份 ERP/CRM/MES 源码；
> 2. `.env.bak-20261007`（真实密钥）、`backend/logs/hub.log`（5.2 MB 生产日志含访问 IP）、
>    `_rollback_bak_20261014/cenkor_db.sql`（1.7 MB 全库备份）、`.stale-apps/`（旧应用残留）；
> 3. `ext` 混合目录里的闭源迁移（workflow 流程定义等）；
> 4. `deploy/baota/cenkor-backend.host.env`（`SECRET_KEY` + `DATABASE_URL` 口令 + S3 密钥）。
>
> 黑名单的致命缺陷是**只覆盖已知项**：新增一个商业应用、加一个环境文件、多一份备份，
> 就漏一次。改用 git 清单后，`gitignore` 是唯一真相，脚本不必跟着改。

### 3.3 五道交付自检

压缩后逐项检查，任何一道不通过都**删掉产物并 `exit 1`**（fail-closed）：

| 自检 | 拦什么 | 通过输出 |
|------|--------|----------|
| 闭源资产 | erp / crm / mes / workflow / src-apps / developer-web / 闭源迁移 / verify_v11 | `自检通过：包内无闭源资产…` |
| 凭据文件 | 任何 `.env` 变体（example 除外）、`*.pem`、`*.key`、`id_rsa*`、`*.bak*` | `自检通过：包内无凭据 / 备份文件…` |
| 运行时垃圾 | `logs/`、`*.log`、`_bak-*`、`_rollback_bak_*`、`.bak.`、`.stale-apps/`、`www/wwwroot/` | `自检通过：包内无运行时垃圾…` |
| 关键文件在不在 | 后端入口、`alembic.ini`、三套前端 `index.html`、`.env.example`、`PACKAGE.md` | `自检通过：关键文件齐全…` |
| 迁移链自洽 | 每个 `down_revision` 都能在包内找到 | `自检通过：包内迁移链自洽…` |

加一道**正向**对账：包内迁移数必须等于 `git ls-files` 的迁移数，多一个就中止
（`已核对迁移数：包内 N 个 = git 跟踪 N 个`）；其余未跟踪文件以 `⚠` 形式列出来供人工确认。

> **交付前自检**（对已有的包也适用）：
>
> ```bash
> P=release/cenkor-admin-core-<version>-<date>.tar.gz
> # ① 闭源 / 凭据 / 垃圾，输出应为空
> tar -tzf "$P" | grep -E 'apps/(erp|crm|mes|workflow|payment)/|developer-web|versions/(erp|crm|mes)/|\.env$|\.env\.|\.log$|\.sql$|_bak|\ .bak' | head
> # ② 迁移链能不能跑
> tar -xzf "$P" -C /tmp && (cd /tmp/$(basename "$P" .tar.gz)/backend && alembic heads)
> # 必须只有一个 head，且与 scripts/check-migration-graph.py --tracked-only 输出一致
> # （不要在文档里写死具体 revision，迁移一加就会过期）
> ```

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
> 重新打包后同样会跑 §3.3 里的五道自检。如果接收方后来自己加了商业应用，
> **把它登记进 `.gitignore` 即可**（打包以 `git ls-files` 为源，不用再改脚本）；
> 若已误提交，自检会拦下并在报错里列出命中的文件。
> 若自检报「迁移链不完整」，说明你排除了某个迁移，但公开迁移仍指向它的 revision——
> 先确认该父迁移是否属闭源（`.gitignore` §155-172），再决定是保留还是连同引用方一起核对。

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
