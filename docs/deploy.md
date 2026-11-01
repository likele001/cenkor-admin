# Cenkor Admin · 部署方案（权威）

> **本文是 cenkor-admin 的唯一权威部署文档。** 其他文档只做引用，不重复端口与路径，
> 以免出现「同一件事三套说法」。
>
> 适用范围：本机生产环境 `admin.cenkor.cn` / `portal.cenkor.cn` / `dev.cenkor.cn`
> 最后核对：**2026-11-01**（逐条对 `ss -tlnp` / `/proc/<pid>/environ` /
> `docker ps -a` / nginx 实际 include 链 / 日志实跑结果核过一遍，不再凭历史记忆）

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
  A1 -->|"/api/ · /api/v1/ws/ · /.app-assets/ · /api/v1/cms/ai/"| API
  A2 -->|"/api/ · /llms.txt"| API
  A3 -->|"/api/"| API
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

| 域名 | 前端根目录 | API 反代（→ `127.0.0.1:8002`） | 备注 |
|---|---|---|---|
| `admin.cenkor.cn` | `frontend/admin-web/dist` | `/api/` · `/api/v1/ws/` · `/.app-assets/` · `/api/v1/cms/ai/` | 另有 `^~ /landing/` → `frontend/` |
| `portal.cenkor.cn` | `frontend/portal-web/dist` | `/api/` · `= /llms.txt` | `/llms.txt` 单独反代到 `/api/v1/public/llms.txt` |
| `dev.cenkor.cn` | `frontend/developer-web/dist` | `/api/` | 规则在 `proxy/` 子目录里，见下方警告 |
| `www.cenkor.cn` | `/www/wwwroot/website`（外部） | `/api/` | 站点文件不属本仓库 |

**nginx 配置位置**：`/www/server/panel/vhost/nginx/<域名>.conf`（宝塔管理，不在仓库内）。

> ⚠️ **宝塔的反代规则可能不在主文件里。** 主文件通过
> `include /www/server/panel/vhost/nginx/proxy/<域名>/*.conf;` 把反代**拆到子目录**。
> 直接 `grep proxy_pass /www/server/panel/vhost/nginx/dev.cenkor.cn.conf` 会**什么都搜不到**，
> 从而误判「这个域名没配反代」——`dev.cenkor.cn` 就踩过这个坑（主文件无 `proxy_pass`，
> 规则实际在 `proxy/dev.cenkor.cn/e77989ed….conf`，`/api/health` 实测 200）。
>
> 判断某域名是否配了反代，要看**展开后的**结果：
>
> ```bash
> nginx -T 2>/dev/null | awk '/server_name dev.cenkor.cn/,/^}/' | grep -E 'proxy_pass|include'
> # 或直接实测
> curl -s -o /dev/null -w '%{http_code}\n' https://dev.cenkor.cn/api/health   # 200 即有
> ```

> 🔴 **`admin.cenkor.cn` 有单独的 `/api/v1/cms/ai/` 段，别漏。**
> 它比通用的 `/api/` 段多三项：`proxy_read_timeout 600s`、`proxy_send_timeout 600s`、
> `proxy_cache off`。AI 生成 / 批量生产是长连接 + 流式返回，落到通用段会**60 秒就 504**。
> 新部署（换域名、重建 vhost）时漏配这一段，表现为「AI 功能一点就超时」，普通接口却全正常。

---

## 3. 端口台账

**下列端口是本机生产实际占用。新增服务前必须避开。**

| 端口 | 用途 | 归属 |
|---|---|---|
| `8002` | cenkor-admin 后端 API | 宝塔 Python 项目 `cenkor` |
| `8008` | **AI 网关**（OpenAI 兼容） | 宝塔 Python 项目 `backend`（`/www/wwwroot/openai/backend`），nginx `python_backend.conf` 反代 |
| `8009` | 容器内 uvicorn 服务 | Docker（cwd `/app`），未挂 nginx 反代，**端口已占** |
| `5432` | PostgreSQL | 宝塔 PG 16（**全平台主库**，多项目共用） |
| `6379` | Redis | 宝塔 Redis（**全平台共用**，db0~db15 按项目划分） |
| `9000` | MinIO API **（控制台同端口）** | systemd `minio` |
| `80` / `443` | nginx | 宝塔 |

> ⚠️ **「MinIO Console 在 9003」是容器时代的说法，宿主机上没有这个端口。**
> 宿主 unit 的启动行只有 `minio server /var/minio/data --address :9000`，**没有
> `--console-address`**，因此控制台与 API 共用 `9000`（新版 MinIO 按路径区分）。
> 实测 `ss -tlnp | grep 9003` 为空、`curl 127.0.0.1:9003` 直接连接失败。
> 需要独立控制台端口时，自己在 unit 里补 `--console-address :9003` 后
> `systemctl daemon-reload && systemctl restart minio`。

> 端口台账以 **`ss -tlnp` 实跑结果**为准，不凭记忆填。8008 / 8009 此前漏记，
> 就是照着"实际占用"一句却漏了两项 —— 新建服务前请先自己跑一遍
> `ss -tlnp | grep -E ':80[0-9][0-9]|:900[0-9]'` 再定端口。

**已被其他项目占用的 Redis 库**：`db1`、`db2`（**占用最多，实测 2900+ key**）、`db9`（AI 网关 `ch_health:*` / `gateway:rr_offset:*`）、`db10`。`db0` 为空。
**cenkor-admin 使用 `db5`。**

> 判断库是否空闲别靠记忆，一条命令看全部：
>
> ```bash
> for n in $(seq 0 15); do printf 'db%-3s %s\n' "$n" "$(redis-cli -p 6379 -n $n DBSIZE 2>/dev/null)"; done
> ```

> ⚠️ 曾踩坑：原配置写的是 `db9`，而宿主 Redis 是全平台共享的，`db9` 属于 AI 网关。
> 迁移时已改到空闲的 `db5`。**改 `REDIS_URL` 前务必先 `redis-cli -n <n> DBSIZE` 确认库是空的。**

**同级其他项目的端口**（互不干扰，仅供对照）：

| 项目 | 端口段 |
|---|---|
| `blog`（容器） | 5434 / 6381 / 9004 / 9005 / 8010 / 5180 / 5190 |
| `fettle`（容器：milvus + minio） | 19530 / 9091 / 9010 / 9011 |
| `lightmes`（宿主机，cwd `/www/wwwroot/lightmes/backend`） | 8000 |
| `cenkormes`（宿主机） | 8500 |

> 上表同样按 `ss -tlnp` 实跑结果填。`fettle` 那组此前漏记（milvus 19530/9091、
> 其配套 minio 9010/9011），新增容器前一样要避开。

---

## 4. 配置：五个落点与优先级 ⭐

**这是最容易出错的地方。** 仓库里存在 5 个长得差不多的配置文件，但**只有 2 个真正生效**。

| # | 位置 | 生效 | 优先级 | 说明 |
|---|---|---|---|---|
| 1 | 宝塔项目环境变量<br>`panel/data/db/site.db` → `sites.id=21` → `project_config.env_list` | ✅ | **最高** | 作为进程环境变量注入，**覆盖** `.env` 文件 |
| 2 | `backend/.env` | ✅ | 补充 | `config.py` 的 `_find_env_file()` 从**当前工作目录**查找 `.env`；宝塔项目的 `path` 是 `backend/`，故读的就是它 |
| 3 | `deploy/baota/cenkor-backend.host.env` | ❌ | — | 仅被 `deploy/baota/start-backend.sh` 使用（脱离宝塔的手工启动路径） |
| 4 | `deploy/examples/env.host.override` | ❌ | — | 被 `deploy/systemd/cenkor-backend.service` 引用 |
| 5 | `/etc/cenkor/env.host.override` | ❌ | — | 同上，systemd unit 里排在最后。**本机该文件不存在**（只有仓库里的模板） |

### 4.1 谁提供什么

| 变量 | 来源 | 值 |
|---|---|---|
| `DATABASE_URL` | 宝塔 `env_list`（权威） | `postgresql+asyncpg://cenkor:***@127.0.0.1:5432/cenkor` |
| `DATABASE_URL_SYNC` | `backend/.env` | `postgresql+psycopg2://cenkor:***@127.0.0.1:5432/cenkor` |
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

### 4.4 `.env` 到底读的是哪一个 ⭐

`core/config.py` 的 `_find_env_file()` **按顺序取第一个存在的**，不是只认当前目录：

```python
candidates = [
    Path.cwd() / ".env",                                      # ① 当前工作目录
    Path.cwd().parent / ".env",                               # ② 上一级
    Path(__file__).resolve().parent.parent.parent.parent / ".env",  # ③ 仓库根
    Path(os.environ.get("HOME", "/tmp")) / ".env",            # ④ HOME
]
```

宝塔项目的 `path` 是 `backend/`，进程 `cwd` 就是那里 → 命中 ①，读 `backend/.env`。

> 🔴 **陷阱**：② 是 `cwd.parent/.env`。如果你在**仓库根**手工起后端（`cd /www/wwwroot/cenkor-admin && uvicorn ...`），
> ① `仓库根/.env` 不存在但 ② 会往上找到 `/www/wwwroot/.env`——**如果那层有 .env，就会静默读到别人的配置**。
> 排查「本地起的服务连错库」时，第一件事是打印实际读到的文件：
>
> ```bash
> cd /www/wwwroot/cenkor-admin/backend && PYTHONPATH=src \
>   /www/server/pyporject_evn/cenkor/bin/python -c \
>   "from cenkor_admin.core.config import _find_env_file; print(_find_env_file())"
> ```

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
| 端点 | `http://127.0.0.1:9000`（**控制台同端口**，本机未单独开 9003，见 §3 说明） |
| 凭据 | `minio` / `<见 backend/.env>` |
| bucket | `cenkor-public`、`cenkor-private`、`scanwork1` |

```bash
systemctl status minio
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9000/minio/health/live   # 200
```

> **MinIO 是必需的，不能省。** 虽然主对象存储已迁到七牛云，但 `cloud_storage_config.keep_local_backup = true`，
> CMS 上传会**双写**一份到本地 MinIO（代码路径：`apps/cms/router.py` 里的 `s3.minio` 单例）。
> 一旦本地 MinIO 挂掉，上传链路会报错。

#### 安装 MinIO（宿主机）

> ⚠️ **官方下载站 `dl.min.io` 已下线**：MinIO 开源版自 2025-10 起停发社区版二进制，
> `https://dl.min.io/server/minio/release/...` 现在返回 **410 Gone**（`mc`、`kes` 同样 410）。
> 网上多数教程里的 `wget https://dl.min.io/...` **已经失效**。
>
> 官方最后一次发版是 **`RELEASE.2025-09-07T16-13-09Z`**，其二进制**仍保留在 GitHub Release 上**，可正常下载。
> （`RELEASE.2025-10-15T17-29-55Z` 那个含安全修复的版本**从未发布任何二进制资产**。）

**方式一：裸二进制 + 自定义 systemd 单元（推荐 —— 与本文档 §5.3 的布局一致）**

MinIO 是**单个静态链接的 Go 二进制**（`file` 显示 `statically linked`、`ldd` 显示
`not a dynamic executable`），不依赖任何系统库 —— **拷到任何同架构机器上直接就能跑**。

```bash
V=RELEASE.2025-09-07T16-13-09Z
B=https://github.com/minio/minio/releases/download/$V
curl -fLo /usr/local/bin/minio "$B/minio.linux-amd64.$V"
curl -fsL "$B/minio.linux-amd64.$V.sha256sum"                  # 对照校验值
sudo chmod +x /usr/local/bin/minio
/usr/local/bin/minio --version                                 # RELEASE.2025-09-07T16-13-09Z
```

> ⚠️ 资产名是 **`minio.linux-amd64.RELEASE.…`**，**不是** `minio` ——
> 直接访问 `.../download/<tag>/minio` 会 **404**。arm64 用 `minio.linux-arm64.RELEASE.…`。
>
> 命令行客户端 `mc` 同理（`mc.linux-amd64.RELEASE.2025-08-13T08-35-41Z`，取自 `minio/mc` 的 Release）。

```ini
# /etc/systemd/system/minio.service
[Unit]
Description=MinIO
After=network.target

[Service]
User=www
Group=www
ExecStart=/usr/local/bin/minio server /var/minio/data --address :9000
Restart=always
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

```bash
sudo mkdir -p /var/minio/data && sudo chown -R www:www /var/minio
sudo systemctl daemon-reload && sudo systemctl enable --now minio
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9000/minio/health/live   # 200
```

**方式二：`.deb` 包（Debian / Ubuntu）**

```bash
V=RELEASE.2025-09-07T16-13-09Z
B=https://github.com/minio/minio/releases/download/$V
curl -fLO "$B/minio_20250907161309.0.0_amd64.deb"
curl -fLO "$B/minio_20250907161309.0.0_amd64.deb.sha256sum"
sha256sum -c minio_20250907161309.0.0_amd64.deb.sha256sum      # 必须输出 OK
sudo dpkg -i minio_20250907161309.0.0_amd64.deb
```

> ⚠️ **这个包只有两个文件**：`/usr/local/bin/minio` 和一个 systemd 单元
> `/lib/systemd/system/minio.service`，**没有 `postinst`** —— 装完**不会**建用户、不会建配置、不会启动。
> 而且包内那个单元写的是 `User=minio-user`、`ExecStart=… $MINIO_OPTS $MINIO_VOLUMES`
> （依赖 `/etc/default/minio`）—— 这两样包里都没有，**直接 `systemctl enable --now minio` 会失败**。
> 补齐前置即可：
>
> ```bash
> sudo useradd -r -s /sbin/nologin minio-user
> sudo mkdir -p /var/minio/data && sudo chown -R minio-user:minio-user /var/minio
> sudo tee /etc/default/minio >/dev/null <<'EOF'
> MINIO_VOLUMES="/var/minio/data"
> MINIO_OPTS="--address :9000 --console-address :9001"
> EOF
> sudo systemctl daemon-reload && sudo systemctl enable --now minio
> ```
>
> 若想直接用本机这套布局（`www` 用户、`/var/minio/data`、不依赖 `/etc/default/minio`），
> 用**方式一**的自定义单元覆盖包内单元即可。
>
> ✅ **实测（Ubuntu 24.04）**：按「**先建用户/目录/配置 → 再装包 → 最后 `enable --now`**」
> 这个顺序可一次成功 —— `is-active: active`、`is-enabled: enabled`、
> `GET /minio/health/live` 返回 **200**、进程用户为 `minio-user`。
>
> ⚠️ **顺序搞反会撞两个坑**（先 `systemctl start` 再补用户时）：
> 先报 **`status=217/USER`**（找不到 `minio-user`），连续失败后 systemd 触发**启动频率限制**，
> 后续无论怎么改都只看到 `Start request repeated too quickly` —— 这**不是**配置又坏了。
> 清掉失败计数即可：
>
> ```bash
> sudo systemctl reset-failed minio && sudo systemctl start minio
> ```

> **需要更新的版本时**：官方二进制已永久停在 `2025-09-07`。若要持续的安全修复，
> 改用 Chainguard 维护的镜像 **`chainguard/minio`** ——
> 它同时发布在 Docker Hub（`chainguard/minio`，国内可用 Docker Hub 加速器代理）与
> `cgr.dev/chainguard/minio`，**两处是同一个镜像（digest 相同）**，目前跟到 `RELEASE.2026-09-22`。

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

# 单个构建（根 package.json 里有这三个别名）
npm run build:admin        # → frontend/admin-web/dist
npm run build:portal       # → frontend/portal-web/dist
npm run build:developer    # → frontend/developer-web/dist

# landing-web 根 package.json 没有别名，需进目录构建
cd frontend/landing-web && npm run build && cd ../..

# 或四个一起（admin / portal / developer / landing）
bash scripts/build-frontends.sh
```

> `scripts/build-frontends.sh` 会透传 `VITE_API_BASE_URL`。**留空即走同域 `/api/`**，
> 这是本机生产的正确取值——填绝对地址会立刻触发 CORS（见 §10.5）。脚本里
> `developer-web` 缺失时是**跳过而不是报错**（该目录属闭源商业资产，可能不在分发版本里）。

宝塔 nginx 的 root 直接指向 `dist`，**构建完即生效**（无需重启 nginx）。

> ⚠️ **不要用 root 跑构建。** root 构建会让 `dist/` 属主变成 `root`，之后 www 用户
> 再构建就会 `PermissionError`。构建后确认属主：
>
> ```bash
> ls -ld frontend/*/dist
> # 期望 www:www；若为 root，修正：
> chown -R www:www frontend/*/dist
> ```
>
> 现状（2026-11-01 实测）：四个 `dist` **均为 `www:www`**，此前记录的
> 「`developer-web/dist` 属主为 root」已不存在。

若 `vue-tsc` 类型检查失败导致 `npm run build` 中断，可用 `npx vite build` 跳过类型检查。

### 6.3 数据库迁移

> 两条链、挂载点、新增迁移的执行顺序与排障，见 [migrations.md](migrations.md)。

**通常不需要手动跑** —— 后端启动时 lifespan 会自动执行 `alembic upgrade heads`（迁移图含公开链与商业应用闭源链）。

手动执行（在宿主机、用生产 venv）：

```bash
cd /www/wwwroot/cenkor-admin/backend
APP_ENV=production PYTHONPATH=src \
  /www/server/pyporject_evn/cenkor/bin/python3 -m alembic upgrade heads
```

查看当前版本：

```bash
sudo -u postgres /www/server/pgsql/bin/psql -p 5432 -d cenkor -tAc "SELECT version_num FROM alembic_version;"
```

### 6.4 重启后端

**唯一正确方式：宝塔面板 → 网站 → Python 项目 → `cenkor` → 重启。**

无面板时的命令行做法 —— **先释放端口，然后什么都不做**：

```bash
# 1. 找到占 8002 的进程
ss -lntp | grep ':8002'
# 2. 杀掉它（只杀占端口的那一个），让端口空出来
kill <pid>
# 3. 不要手动拉起，等宝塔自愈重新接管（约 10~60 秒）
sleep 30 && ss -lntp | grep ':8002' && ps -o user= -p $(ss -lntp | grep ':8002' | grep -oP 'pid=\K[0-9]+' | head -1)
```

> 🔴 **绝对不要 `nohup uvicorn ... &` 手动起后端。** 宝塔守护进程（`auto_run=true`）认不出
> 手动起的进程（用户 / 参数不匹配），会在**每 120 秒拉起一个新实例再杀掉**，表现为
> `error.log` 里零 ERROR 却**每 2 分钟刷一轮 `app.starting`**。判断方法：看日志有没有严格
> 120 秒周期的启动行。

> 🔴 **`scripts/restart-backend-host.sh` 不能在本机用。** 这个脚本是「容器 + 裸进程
> baota-static」时代的遗留，它做的事恰恰是上面禁止的：`kill` 掉占 8002 的进程 →
> `nohup uvicorn --workers 2 &` 裸起 → 日志写 `/tmp/cenkor-uvicorn.log`。
> 而且它的缺省值与宿主机化之后的生产**全不一致**：
>
> | 脚本缺省 | 生产实际 |
> |---|---|
> | `REDIS_URL=…/0` | `…/5` |
> | `S3_ENDPOINT=http://127.0.0.1:9002` | `http://127.0.0.1:9000` |
> | 会去读 `docker inspect cenkor-postgres` 的密码 | 容器已删除，读不到 |
>
> 在宝塔托管环境下执行它 = 手动抢端口 + 连错 Redis 库 → 宝塔自愈反复
> `address already in use`。脚本现已加运行前拦截（检测到宝塔托管会拒绝并提示），
> 但**文档这边也请别再推荐它**。它只在 `native_deploy.md` 的裸机 systemd 路线下有意义。

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
#    注意：error.log 只装「当天」，宝塔每天 00:00 切成 error.log-YYYYMMDD(.gz)。
#    当天没重启过的话，启动日志在昨天的文件里——只 grep error.log 会以为「什么都没打」。
zgrep -hE 'app\.starting|db\.ok|migration\.ok|redis\.ok|s3\.buckets\.ready' \
  /www/wwwlogs/python/cenkor/error.log /www/wwwlogs/python/cenkor/error.log-* 2>/dev/null | tail -5
```

期望看到一组（同一次启动，时间戳连续）：

```
2026-11-01 02:31:23 [info] app.starting      env=production version=0.3.0
2026-11-01 02:31:23 [info] db.ok             dialect=postgresql
2026-11-01 02:31:24 [info] migration.ok      result=...
2026-11-01 02:31:24 [info] redis.ok
2026-11-01 02:31:25 [info] s3.buckets.ready  public=scanwork1
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
sudo -u postgres $PG/pg_restore -p 5432 -d cenkor --no-owner --no-privileges --role=cenkor -j 4 <dump文件>
```

> ⚠️ 工具名是 **`pg_restore`**，不是 `restore`。`/www/server/pgsql/bin/` 下只有
> `psql` / `pg_dump` / `pg_dumpall` / `pg_restore` / `pg_waldump` 这几个可执行文件，
> 写成 `$PG/restore` 会直接 `No such file or directory`。
>
> 🔴 第一行 `DROP DATABASE` 会**整库删除**。执行前先确认 dump 文件存在且非空
> （`ls -l`、`pg_restore -l <dump> | head`），这是全平台主库，误删会同时影响
> `ai_platform` 之外的同实例其它库的**操作面**（虽然 DROP 只删 cenkor，但停服期间全平台都在等）。

### 8.4 回滚到「数据在容器」的旧架构

> 🔴 **先看结论：这条路现在走不通了。** 2026-09-25 迁移时确实留了资产，但**大部分已经失效**，
> 下表是 2026-11-01 的实测状态。**不要以为出了事能一键回滚。**

| 资产 | 位置 | 2026-11-01 实测 |
|---|---|---|
| 容器库导出 | `/tmp/pg-backup/cenkor_container_*.dump` | ❌ **已丢失**（`/tmp` 被清理，整个目录不存在） |
| 空壳库 dump | `/tmp/pg-backup/cenkor_host_empty_*.dump` | ❌ **已丢失**（同上） |
| 4 个容器 | `cenkor-postgres` / `cenkor-redis` / `cenkor-minio` / `cenkor-admin-web` | ❌ **已全部删除**（`docker ps -a \| grep cenkor` 为空） |
| 容器数据卷 | `cenkor-admin_postgres-data` / `_redis-data` / `_minio-data` | ✅ **仍在**（数据可能可以救出来） |
| `.env` 备份 | `backend/.env.bak_<时间戳>` | 🟡 有备份，但**没有迁移当时那份**（现存最早为 10-07，迁移是 09-25） |
| 宝塔 `site.db` 备份 | `/root/backup/site.db.bak_*` | ✅ `site.db.bak_20260925123940` 仍在（迁移当天） |

**真要回滚，得重建容器**（`docker start` 已经没对象可起）：

```bash
# 数据卷还在，可以用一次性容器把数据捞出来，而不是"回滚整个架构"
docker run --rm -v cenkor-admin_postgres-data:/var/lib/postgresql/data \
  -v /tmp/rescue:/backup alpine \
  tar czf /backup/pgdata-$(date +%F).tgz -C /var/lib/postgresql/data .
```

> ⚠️ **不要用 `docker compose up -d` 重建。** minio 服务用的是 `:latest` tag，compose 会尝试
> 拉 `quay.io/minio/minio:latest` 并因 **401** 失败，**整条命令中止，连 pg/redis 都起不来**。
> 官方社区版二进制自 2025-10 起已停发（见 §5.3），拉不到是必然的。
>
> **更现实的建议**：别指望回滚到容器架构。正确做法是保持现在的 §8.1 / §8.2 日常备份，
> 出问题用 `pg_restore` 恢复到宿主机。

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

**现状（2026-11-01 核对）**：`backend/.env` 的 `CORS_ORIGINS` 是一长串 `*.cenkor.cn`，
含 `www.cenkor.cn` / `mes.*` / `labor.*` / `fettle.*` 等，
**确实没有 `admin.cenkor.cn` / `portal.cenkor.cn` / `dev.cenkor.cn`**。

**为什么不影响**：三个前端与 API **同域**（都走 `<域名>/api/`，由 nginx 反代到 8002，
`proxy_set_header Host $host` 透传），浏览器视为同源，**不触发 CORS 预检**。

**什么时候才会炸**：把任一端点的 `VITE_API_BASE_URL` 改成绝对地址（例如指向
`https://api.cenkor.cn` 直连），立刻变成跨域 → 缺头 → 全部接口失败。
`scripts/build-frontends.sh` 之所以强调「留空走同域」，就是为了避开这个坑（见 §6.2）。

> 真要改：在 `CORS_ORIGINS` 里补三个域名，**并同时改宝塔 `env_list`**（它优先级更高，见 §4.2）。

### 10.6 `dev.cenkor.cn` 的 `/api/` 反代（**已确认存在**）

此前本文写过「`dev.cenkor.cn` 没有任何 `proxy_pass`」——**这是错的**，原因是只 grep 了
vhost 主文件。宝塔把反代规则拆在子目录里：

```
/www/server/panel/vhost/nginx/dev.cenkor.cn.conf          ← 主文件，无 proxy_pass
  └─ include .../proxy/dev.cenkor.cn/*.conf               ← 真正规则在这
       e77989ed….conf → location /api/ { proxy_pass http://127.0.0.1:8002/api/; }
```

**实测**：`https://dev.cenkor.cn/api/health` → `200 {"status":"ok",…}`、
`/api/v1/public/portal/auth/login-config` → `200`。开发者门户的 `baseURL` 取
`import.meta.env.VITE_API_BASE_URL || ''`（默认空 → 同域相对路径），与该反代正好配套。

> 通用教训：**判断「某域名是否配了反代」不要 grep 主文件**，用 `nginx -T` 看展开结果，
> 或者干脆 `curl` 实测（见 §2 的警告块）。

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
| MinIO | 宿主机原生 | 9000（控制台同端口；当日记的 9003 已不存在） |

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
