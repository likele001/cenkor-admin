# Cenkor Admin · 部署方案（权威）

> **本文是 cenkor-admin 的唯一权威部署文档。** 其他文档只做引用，不重复端口与路径，
> 以免出现「同一件事三套说法」。
>
> 适用范围：本机生产环境 `admin.cenkor.cn` / `portal.cenkor.cn` / `dev.cenkor.cn`
> 最后核对：2026-09-25（宿主机化改造完成）

---

## 0. 一句话现状

cenkor-admin 生产环境**全部跑在宿主机上**，由**宝塔面板**托管，**不使用 Docker**。

| | 位置 | 说明 |
|---|---|---|
| 应用进程 | **宿主机** | 宝塔「Python 项目」`cenkor`，用户 `www`，端口 `8002` |
| PostgreSQL / Redis / MinIO | **宿主机** | 宝塔软件商店安装的原生服务 |
| 前端静态文件 | **宿主机** | 宝塔 nginx 直接 serve `frontend/*/dist` |
| 对象存储（主） | **云端七牛云 Kodo** | 本地 MinIO 仅作双写备份 |

Docker 路线**仅作为「打包交付给别人 / 多环境一致性验证」的可选路径保留**，见 [§9](#9-docker-模式可选交付路径)。

---

## 1. 架构总览

```mermaid
flowchart TB
  B[浏览器]

  subgraph NG[宝塔 nginx]
    A1["admin.cenkor.cn<br/>→ frontend/admin-web/dist"]
    A2["portal.cenkor.cn<br/>→ frontend/portal-web/dist"]
    A3["dev.cenkor.cn<br/>→ frontend/developer-web/dist"]
    A4["www.cenkor.cn<br/>→ /www/wwwroot/website（外部站）"]
  end

  subgraph HOST[宿主机 127.0.0.1]
    API["宝塔 Python 项目 cenkor<br/>uvicorn :8002 · user=www"]
    PG["PostgreSQL 16 :5432<br/>db=cenkor"]
    RD["Redis 7 :6379<br/>db=5"]
    MN["MinIO :9000<br/>cenkor-public / private / scanwork1"]
  end

  QN[七牛云 Kodo<br/>bucket scanwork1 · CDN img1.images.023ent.net]

  B --> NG
  A1 -->|"/api/ · /api/v1/ws/ · /.app-assets/"| API
  A2 -->|"/api/"| API
  A4 -->|"/api/"| API
  API --> PG
  API --> RD
  API --> MN
  API -->|"主存储"| QN
  API -.->|"keep_local_backup 双写"| MN
```

> `www.cenkor.cn` 的站点根目录是 `/www/wwwroot/website`，**不属于本仓库**，
> 只是把 `/api/` 反代到了同一个后端。改本仓库的代码不会影响它的静态页面。

### 组件职责

| 组件 | 位置 | 职责 |
|---|---|---|
| **backend** | `backend/` | FastAPI + SQLAlchemy 2.0 async + Celery，提供 REST API / RBAC / CMS / 应用中心 / 审计 |
| **admin-web** | `frontend/admin-web/` | 运营后台 SPA |
| **portal-web** | `frontend/portal-web/` | 终端用户 SPA（注册 / 登录 / 资料） |
| **developer-web** | `frontend/developer-web/` | 开发者门户 SPA（开发文档 + 提交应用） |
| **landing-web** | `frontend/landing-web/` | 落地页，挂在 `admin.cenkor.cn/landing/` 下 |
| **design-tokens** | `frontend/design-tokens/` | 设计变量，通过 CSS exports 发布，无需构建 |

---

## 2. 域名台账

| 域名 | 前端根目录 | API 反代 | 备注 |
|---|---|---|---|
| `admin.cenkor.cn` | `frontend/admin-web/dist` | `/api/` `/api/v1/ws/` `/.app-assets/` → `127.0.0.1:8002` | 另有 `^~ /landing/` → `frontend/` |
| `portal.cenkor.cn` | `frontend/portal-web/dist` | `/api/` → `127.0.0.1:8002` | |
| `dev.cenkor.cn` | `frontend/developer-web/dist` | ⚠️ **当前无 `/api/` 反代**，见 [§10.6](#106-devcenkercn-无-api-反代) | |
| `www.cenkor.cn` | `/www/wwwroot/website`（外部） | `/api/` → `127.0.0.1:8002` | 站点文件不属本仓库 |

**nginx 配置位置**：`/www/server/panel/vhost/nginx/<域名>.conf`（宝塔管理，不在仓库内）。

> ⚠️ **`dev.cenkor.cn` 缺 `/api/` 反代**：如果开发者门户需要调用后端接口，它的
> 请求会打到静态文件 404。需确认开发者门户的 API 地址是绝对 URL 还是同域 `/api/`。

---

## 3. 端口台账

**下列端口是本机生产实际占用。新增服务前必须避开。**

| 端口 | 用途 | 归属 |
|---|---|---|
| `8002` | cenkor-admin 后端 API | 宝塔 Python 项目 `cenkor` |
| `5432` | PostgreSQL | 宝塔 PG 16（**全平台主库**，多项目共用） |
| `6379` | Redis | 宝塔 Redis（**全平台共用**，db0~db15 按项目划分） |
| `9000` | MinIO API | systemd `minio` |
| `9003` | MinIO Console | systemd `minio` |
| `80` / `443` | nginx | 宝塔 |

**已被其他项目占用的 Redis 库**：`db1`、`db2`、`db9`（AI 网关 `ch_health:*` / `gateway:rr_offset:*`）、`db10`。
**cenkor-admin 使用 `db5`。**

> ⚠️ 曾踩坑：原配置写的是 `db9`，而宿主 Redis 是全平台共享的，`db9` 属于 AI 网关。
> 迁移时已改到空闲的 `db5`。**改 `REDIS_URL` 前务必先 `redis-cli -n <n> DBSIZE` 确认库是空的。**

**同级其他项目的端口**（互不干扰，仅供对照）：

| 项目 | 端口段 |
|---|---|
| `blog`（容器） | 5434 / 6381 / 9004 / 9005 / 8010 / 5180 / 5190 |
| `lightmes`（宿主机） | 8000 |
| `cenkormes`（宿主机） | 8500 |

---

## 4. 配置：五个落点与优先级 ⭐

**这是最容易出错的地方。** 仓库里存在 5 个长得差不多的配置文件，但**只有 2 个真正生效**。

| # | 位置 | 生效 | 优先级 | 说明 |
|---|---|---|---|---|
| 1 | 宝塔项目环境变量<br>`panel/data/db/site.db` → `sites.id=21` → `project_config.env_list` | ✅ | **最高** | 作为进程环境变量注入，**覆盖** `.env` 文件 |
| 2 | `backend/.env` | ✅ | 补充 | `config.py` 的 `_find_env_file()` 从**当前工作目录**查找 `.env`；宝塔项目的 `path` 是 `backend/`，故读的就是它 |
| 3 | `deploy/baota/cenkor-backend.host.env` | ❌ | — | 仅被 `deploy/baota/start-backend.sh` 使用（脱离宝塔的手工启动路径） |
| 4 | `deploy/examples/env.host.override` | ❌ | — | 被 `deploy/systemd/cenkor-backend.service` 引用 |
| 5 | `/etc/cenkor/env.host.override` | ❌ | — | 同上，systemd unit 里排在最后 |

### 4.1 谁提供什么

| 变量 | 来源 | 值 |
|---|---|---|
| `DATABASE_URL` | 宝塔 `env_list`（权威） | `postgresql+asyncpg://cenkor:***@127.0.0.1:5432/cenkor` |
| `DATABASE_URL_SYNC` | `backend/.env` | `postgresql://cenkor:***@127.0.0.1:5432/cenkor` |
| `REDIS_URL` | 宝塔 `env_list`（权威） | `redis://127.0.0.1:6379/5` |
| `S3_ENDPOINT` | 宝塔 `env_list`（权威） | `http://127.0.0.1:9000` |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | 宝塔 `env_list` | `minio` / `***` |
| `S3_BUCKET_PUBLIC` / `S3_BUCKET_PRIVATE` | `backend/.env` | `cenkor-public` / `cenkor-private` |
| `SECRET_KEY` | `backend/.env` | ⚠️ 生产密钥，勿外泄 |
| `CORS_ORIGINS` | `backend/.env` | 见 [§10.5](#105-cors_origins-缺本仓库自有域名) |
| `APP_ENV` | 宝塔 `env_list` | `production` |
| `PYTHONPATH` | 宝塔 `env_list` | `/www/wwwroot/cenkor-admin/backend/src` |

### 4.2 改配置的正确姿势

> **改一处不够。** `DATABASE_URL` / `REDIS_URL` / `S3_ENDPOINT` 这三项在**宝塔 `env_list`**
> 和 **`backend/.env`** 里各有一份，必须**同时改**，否则宝塔那份会静默覆盖文件那份，
> 排查时会被 `.env` 的内容误导。

推荐流程：

```bash
# 1. 改 backend/.env（用编辑器，改完确认属主仍是 www:www）
vi /www/wwwroot/cenkor-admin/backend/.env

# 2. 改宝塔 env_list —— 用面板网页改，或谨慎地直接改 sqlite：
#    宝塔面板 → 网站 → Python 项目 → cenkor → 环境变量
#    （改前先备份：cp /www/server/panel/data/db/site.db /root/backup/site.db.bak_$(date +%F_%T)）

# 3. 重启后端（见 §6.4）

# 4. 核对**进程实际**拿到的值 —— 这是唯一可信的校验
PID=$(ss -lntp | grep ':8002' | grep -oP 'pid=\K[0-9]+' | head -1)
tr '\0' '\n' < /proc/$PID/environ | grep -E '^(DATABASE_URL|REDIS_URL|S3_ENDPOINT)='
```

### 4.3 其余三个落点怎么处理

它们**不影响生产**，但是「另一条路」的模板，会误导后来人（迁移时就发现三处的 Redis 库号
分别是 `db0` / `db9` / 实际 `db5`）。**改配置时顺手对齐**，模板文件（`.example`）一并更新。

---

## 5. 依赖服务

### 5.1 PostgreSQL

| 项 | 值 |
|---|---|
| 安装位置 | `/www/server/pgsql`（宝塔软件商店） |
| 版本 | 16.x |
| 监听 | `127.0.0.1:5432`（`listen_addresses` 含 `172.17.0.1`，供容器访问） |
| 库 / 角色 | `cenkor` / `cenkor` |
| 认证 | `pg_hba.conf` 已配 `host cenkor cenkor 0.0.0.0/0 md5` |

> ⚠️ **这是全平台主库**，里面还有 `ai_platform`、`api`、`openai`、`labor`、`standalone` 等库。
> 任何 `DROP DATABASE` / 大范围清理**务必先确认库名**。

初始化（仅首次）：

```bash
PG=/www/server/pgsql/bin
sudo -u postgres $PG/psql -p 5432 -c "CREATE ROLE cenkor LOGIN PASSWORD '<密码>';"
sudo -u postgres $PG/psql -p 5432 -c "CREATE DATABASE cenkor OWNER cenkor TEMPLATE template0 \
  ENCODING 'UTF8' LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8';"
```

> 本机只有 `C.utf8` locale（`en_US.utf8` 未生成），建库时用 `C.UTF-8`。
> 建表由后端 lifespan 自动完成，无需手动跑迁移。

### 5.2 Redis

| 项 | 值 |
|---|---|
| 安装位置 | `/www/server/redis`（宝塔软件商店，systemd 托管） |
| 监听 | `127.0.0.1:6379` |
| 使用库 | **db5** |

```bash
redis-cli -p 6379 ping              # PONG
redis-cli -p 6379 -n 5 DBSIZE       # 本项目的 key 数
```

### 5.3 MinIO（本地对象存储 / 双写备份）

| 项 | 值 |
|---|---|
| 托管 | systemd unit `minio`（unit 文件在 `/etc/systemd/system/minio.service`） |
| 数据目录 | `/var/minio/data` |
| 端点 | `http://127.0.0.1:9000`（Console `9003`） |
| 凭据 | `minio` / `<见 backend/.env>` |
| bucket | `cenkor-public`、`cenkor-private`、`scanwork1` |

```bash
systemctl status minio
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9000/minio/health/live   # 200
```

> **MinIO 是必需的，不能省。** 虽然主对象存储已迁到七牛云，但 `cloud_storage_config.keep_local_backup = true`，
> CMS 上传会**双写**一份到本地 MinIO（代码路径：`apps/cms/router.py` 里的 `s3.minio` 单例）。
> 一旦本地 MinIO 挂掉，上传链路会报错。

### 5.4 对象存储（七牛云 Kodo）

| 项 | 值 |
|---|---|
| provider | `qiniu`（存在数据库 `cloud_storage_config` 表，**不是环境变量**） |
| bucket | `scanwork1` |
| endpoint | `https://s3.cn-south-1.qiniucs.com` |
| CDN | `img1.images.023ent.net` |
| 凭据 | 加密存于 `cloud_storage_config.creds_qiniu`（AES 加密，密钥来自 `SECRET_KEY`） |

> ⚠️ **两个认知陷阱**：
> 1. **`S3_ENDPOINT` 环境变量不影响主存储。** 主存储由数据库里的云存储配置决定
>    （`core/storage.py` 的 `public_bucket()` 优先读 `cloud_storage_config`），
>    `S3_ENDPOINT` 只决定**本地备份用的 MinIO**。
> 2. **`S3_BUCKET_PUBLIC` 也可能不生效。** 启动日志里出现 `public=scanwork1` 而不是
>    `cenkor-public`，就是因为 bucket 名来自数据库配置。看到这个**不是 bug**。

---

## 6. 部署与发布

### 6.1 后端

| 项 | 值 |
|---|---|
| 托管方式 | 宝塔「Python 项目」 |
| 项目名 / ID | `cenkor` / `21` |
| 项目路径 | `/www/wwwroot/cenkor-admin/backend` |
| 运行用户 | `www` |
| Python | 虚拟环境 `/www/server/pyporject_evn/cenkor/bin/python3` |
| 端口 | `8002` |
| 自动启动 | `auto_run = true`（宝塔守护） |
| 日志 | `/www/wwwlogs/python/cenkor/error.log` |

**改了后端代码 → 必须在宝塔面板重启项目才生效。**

### 6.2 前端

```bash
cd /www/wwwroot/cenkor-admin

# 单个构建
npm run build:admin        # → frontend/admin-web/dist
npm run build:portal       # → frontend/portal-web/dist
npm run build:developer    # → frontend/developer-web/dist

# 或全部一起
bash scripts/build-frontends.sh
```

宝塔 nginx 的 root 直接指向 `dist`，**构建完即生效**（无需重启 nginx）。

> ⚠️ **不要用 root 跑构建。** root 构建会让 `dist/` 属主变成 `root`，之后 www 用户
> 再构建就会 `PermissionError`。构建后确认属主：
>
> ```bash
> ls -ld frontend/*/dist
> # 若为 root，修正：
> chown -R www:www frontend/*/dist
> ```
>
> 现状：`frontend/developer-web/dist` 属主为 `root`，**待修正**。

若 `vue-tsc` 类型检查失败导致 `npm run build` 中断，可用 `npx vite build` 跳过类型检查。

### 6.3 数据库迁移

**通常不需要手动跑** —— 后端启动时 lifespan 会自动执行 `alembic upgrade head`。

手动执行（在宿主机、用生产 venv）：

```bash
cd /www/wwwroot/cenkor-admin/backend
APP_ENV=production PYTHONPATH=src \
  /www/server/pyporject_evn/cenkor/bin/python3 -m alembic upgrade head
```

查看当前版本：

```bash
sudo -u postgres /www/server/pgsql/bin/psql -p 5432 -d cenkor -tAc "SELECT version_num FROM alembic_version;"
```

### 6.4 重启后端

**由人在宝塔面板操作**：宝塔面板 → 网站 → Python 项目 → `cenkor` → **重启**。

命令行重启（无面板时）：

```bash
bash scripts/restart-backend-host.sh
```

> ⚠️ **不要手动 `kill` 后再裸起 uvicorn 进程。** 宝塔守护进程（`auto_run=true`）会
> 认不出手动起的进程（用户/参数不匹配），于是在**每 120 秒拉起一个新实例再杀掉**，
> 表现为 `error.log` 里零 ERROR 却**每 2 分钟刷一轮 `app.starting`**。
> 判断方法：看日志有没有严格 120 秒周期的启动行。

---

## 7. 验证清单

改完部署后逐项过一遍：

```bash
# 1. 进程在跑，且用户是 www、环境变量指向宿主机
PID=$(ss -lntp | grep ':8002' | grep -oP 'pid=\K[0-9]+' | head -1)
ps -o user= -p $PID                       # 期望 www
tr '\0' '\n' < /proc/$PID/environ | grep -E '^(DATABASE_URL|REDIS_URL|S3_ENDPOINT)='

# 2. 三个域名健康检查
for d in admin portal dev; do
  printf '%-30s ' "https://$d.cenkor.cn/api/health"
  curl -s -o /dev/null -w '%{http_code}\n' --max-time 8 "https://$d.cenkor.cn/api/health"
done

# 3. 依赖服务
sudo -u postgres /www/server/pgsql/bin/psql -p 5432 -d cenkor -tAc "SELECT count(*) FROM pg_tables WHERE schemaname='public';"
redis-cli -p 6379 -n 5 DBSIZE
curl -s -o /dev/null -w 'minio %{http_code}\n' http://127.0.0.1:9000/minio/health/live

# 4. 后端启动日志里应出现四项 ok
grep -E 'db\.ok|migration\.ok|redis\.ok|s3\.buckets\.ready' /www/wwwlogs/python/cenkor/error.log | tail -4
```

> ⚠️ **不要只看 `/api/health`。** 它可能在后端启动阶段就返回 200，掩盖依赖故障。
> `/api/auth/login` 返回 **422** 是**正常**的（参数校验发生在查库之前），
> 首页返回 **200** 也只说明静态文件在（宝塔托管 dist）。
> **数据库真的挂了，最可靠的信号是 `error.log` 里的 `[Errno 111] Connection refused`。**

---

## 8. 备份与回滚

### 8.1 日常备份

```bash
bash scripts/backup.sh
```

### 8.2 手工备份数据库

```bash
PG=/www/server/pgsql/bin
TS=$(date +%Y%m%d%H%M)
mkdir -p /tmp/pg-backup && chmod 777 /tmp/pg-backup
sudo -u postgres $PG/pg_dump -p 5432 -d cenkor -Fc -f /tmp/pg-backup/cenkor_$TS.dump
```

> `/root` 对 `postgres` 用户不可写，备份目录用 `/tmp` 或先 `chmod`。

### 8.3 恢复

```bash
PG=/www/server/pgsql/bin
sudo -u postgres $PG/psql -p 5432 -d postgres -c "DROP DATABASE IF EXISTS cenkor;"
sudo -u postgres $PG/psql -p 5432 -d postgres -c "CREATE DATABASE cenkor OWNER cenkor \
  TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8';"
sudo -u postgres $PG/restore -p 5432 -d cenkor --no-owner --no-privileges --role=cenkor -j 4 <dump文件>
```

### 8.4 回滚到「数据在容器」的旧架构

2026-09-25 迁移时**保留了完整回滚路径**：

| 资产 | 位置 | 说明 |
|---|---|---|
| 容器库导出 | `/tmp/pg-backup/cenkor_container_*.dump` | 迁移前容器 PG 的全量 dump |
| 空壳库 dump | `/tmp/pg-backup/cenkor_host_empty_*.dump` | 宿主 PG 迁移前的原始状态 |
| 4 个容器 | `cenkor-postgres` / `cenkor-redis` / `cenkor-minio` / `cenkor-admin-web` | **未删除**，数据卷保留 |
| `.env` 备份 | `backend/.env.bak_<时间戳>` | 配置切换前的版本 |
| 宝塔 `site.db` 备份 | `/root/backup/site.db.bak_*` | `env_list` 切换前的版本 |

回滚步骤：恢复 `env_list` 与 `.env` → `docker start censkor-postgres cenkor-redis cenkor-minio` → 重启宝塔项目。

> ⚠️ **恢复容器不要用 `docker compose up -d`。** minio 服务用的是 `:latest` tag，
> compose 会尝试拉 `quay.io/minio/minio:latest` 并因 **401** 失败，
> 导致**整条命令中止，连 pg/redis 都起不来**。
> 正确做法：`docker start cenkor-postgres cenkor-redis cenkor-minio`。

---

## 9. Docker 模式（可选交付路径）

> **本机生产不使用 Docker。** 保留这套编排是为了：把系统**交付给别人**时一键起全栈、
> 以及在干净环境里验证「多环境一致性」。`blog` 项目仍在用容器，相关文件不要删。

### 9.1 compose 文件对照

| 文件 | 用途 | 状态 |
|---|---|---|
| `docker-compose.yml` | 默认：中间件 + 后端 + admin-web dev server + nginx | ⚠️ 默认会占 `80/443` |
| `docker-compose.fullstack.yml` | 全栈一条命令（含前端构建） | 交付演示用 |
| `docker-compose.prod.yml` | Docker 自管 nginx 生产 | ⚠️ 硬编码 `80/443` |
| `docker-compose.baota.yml` | 宝塔反代 Docker 前端 | ⚠️ 端口默认值与生产冲突 |
| `docker-compose.baota-static.yml` | 只起后端+中间件，前端走宝塔静态 | 旧默认路径 |
| `docker-compose.addon-website.yml` | 官网 CMS 附加组件 | 可选 |

**在本机使用前**，务必按 [§3 端口台账](#3-端口台账) 检查端口冲突，或用 `--env-file` 覆盖端口。

### 9.2 交付给别人时的最小路径

```bash
cp .env.example .env          # 改 POSTGRES_PASSWORD / MINIO_ROOT_PASSWORD / SECRET_KEY
docker compose -f docker-compose.fullstack.yml --project-name cenkor-admin-fullstack up -d --build
```

详见 [`fullstack_deploy.md`](fullstack_deploy.md)。

---

## 10. 排障手册

### 10.1 首页能开但功能全挂

**症状**：`admin.cenkor.cn` 首页 200，登录页能显示，但登录报错 / 数据加载失败。

**根因**：静态文件由宝塔 nginx 直接 serve，**跟后端无关**。首页 200 完全不能说明后端健康。

**排查**：

```bash
tail -50 /www/wwwlogs/python/cenkor/error.log | grep -iE 'error|refused|timeout'
```

### 10.2 日志里 `[Errno 111] Connection refused`

**根因**：后端连不上 PostgreSQL / Redis / MinIO —— 依赖服务挂了，或配置指向了不存在的端口。

**排查顺序**：`ss -lntp | grep -E ':(5432|6379|9000)'` 确认服务在听 → 核对进程环境变量（§4.2 第 4 步）。

### 10.3 `error.log` 零 ERROR，但每 2 分钟刷一轮启动日志

**根因**：宝塔守护进程认不出实际在跑的进程（用户或参数不匹配），反复拉起新实例。
**处理**：在宝塔面板重启项目，让进程回到守护进程的管辖范围。

### 10.4 登录接口返回 422

**这是正常的**，不是故障。422 是参数校验失败（请求体格式不对），校验发生在查库之前。
用真实请求体测试才能判断后端是否正常。

### 10.5 `CORS_ORIGINS` 缺本仓库自有域名

**现状**：`backend/.env` 的 `CORS_ORIGINS` 里有一长串 `*.cenkor.cn` 域名，
但**没有 `admin.cenkor.cn` / `portal.cenkor.cn` / `dev.cenkor.cn`**。

**影响判断**：`admin` / `portal` 的前端与 API **同域**（都走 `<域名>/api/`，由 nginx 反代到 8002），
浏览器视为同源，**不触发 CORS**，所以目前不影响。
但 `dev.cenkor.cn` 若直连后端（见 10.6），就会因缺 CORS 头而失败。

**待确认**，不要盲改。

### 10.6 `dev.cenkor.cn` 无 `/api/` 反代

**现状**：`dev.cenkor.cn` 的 vhost 只 serve `frontend/developer-web/dist`，
**没有任何 `proxy_pass`**，与 `admin` / `portal` 不一致。

**影响**：开发者门户若用同域 `/api/` 调后端，请求会落到静态文件 404；
若用绝对 URL 则不受影响（但需 CORS，见 10.5）。

**待确认**，先核对 `frontend/developer-web` 里的 API base 配置。

### 10.7 上传图片报错

**排查**：① 七牛云配置（数据库 `cloud_storage_config.creds_qiniu` 能否解密）；
② 本地 MinIO 是否存活（`systemctl status minio`）；
③ `scanwork1` bucket 是否存在。

### 10.8 PostgreSQL 连接数打满

```bash
sudo -u postgres /www/server/pgsql/bin/psql -p 5432 -tAc \
  "SELECT datname, usename, count(*) FROM pg_stat_activity WHERE datname IS NOT NULL GROUP BY 1,2 ORDER BY 3 DESC;"
```

> ⚠️ 宿主 PG 是**全平台共用**的，其他项目的连接也会算在内。

---

## 附录 A：从 Docker 迁移到宿主机的记录（2026-09-25）

### 迁移前

| 组件 | 位置 | 端口 |
|---|---|---|
| 后端 | 宿主机（宝塔） | 8002 |
| PostgreSQL | 容器 `cenkor-postgres` | 5433 |
| Redis | 容器 `cenkor-redis` | 6380 / db9 |
| MinIO | 容器 `cenkor-minio` | 9002 / 9003 |

### 迁移后

| 组件 | 位置 | 端口 |
|---|---|---|
| 后端 | 宿主机（宝塔，**不变**） | 8002 |
| PostgreSQL | 宿主机原生 | 5432 |
| Redis | 宿主机原生 | 6379 / **db5** |
| MinIO | 宿主机原生 | 9000 / 9003 |

### 做法

1. `pg_dump -Fc` 从容器导出 `cenkor` 库 → `pg_restore` 导入宿主 PG
2. 逐表 `count(*)` 比对，**202 张表全等**，`alembic_version` 两边一致
3. 用 `mc` 在宿主 MinIO 建 3 个 bucket + 专用用户，`mc mirror` 镜像对象
4. Redis 从 `db9` 改到空闲的 `db5`
5. 改宝塔 `env_list` 与 `backend/.env`
6. **用 www 身份起临时实例（8013）预检**，确认四项 ok 且接口响应与生产逐条一致
7. 重启生产，验证通过

### 过程中的两个教训

- **配置落点分散且互相不一致**（Redis 库号有 `db0` / `db9` / 实际 `db5` 三种）→ 本文 §4 就是为此而写
- **迁移期间误停了数据层容器**，导致生产报 `Connection refused`；恢复时发现 `docker compose up -d`
  会被 minio 的 `:latest` tag 卡住（401），只能用 `docker start`

---

## 附录 B：相关文档

| 文档 | 说明 |
|---|---|
| [`index.md`](index.md) | 文档总索引 |
| [`fullstack_deploy.md`](fullstack_deploy.md) | Docker 全栈部署（**可选交付路径**） |
| [`native_deploy.md`](native_deploy.md) | 裸机 systemd 部署（本机未采用） |
| [`domain_setup.md`](domain_setup.md) | 域名绑定与 SSL |
| [`upgrade.md`](upgrade.md) | 版本升级 |
| [`packaging.md`](packaging.md) | 打包交付 |
| [`dev_guide.md`](dev_guide.md) | 二次开发 |
| [`architecture.md`](../architecture.md) | 架构设计 |

站点版：<https://docs.user.023ent.net/cenkor-admin/>
