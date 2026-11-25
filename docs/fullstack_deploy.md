# Cenkor Admin · 全栈容器化部署（含前端，一条命令）

> ⚠️ **本文描述的不是本机生产架构。**
>
> 本机生产是**纯宿主机 + 宝塔**部署 —— 后端、PostgreSQL、Redis、MinIO 全部跑在宿主机上，
> **不使用 Docker**。权威文档见 [`deploy.md`](deploy.md)。
>
> 本文保留是为了「把系统交付给别人」或「在干净环境里验证」。其中的容器端口
> （`5433` / `6380` / `9002`）是 **Docker 映射端口**，与本机生产的宿主机端口
> （`5432` / `6379` / `9000`）**不是一回事**，请勿混用。


> 在原有「后端裸机 + dev Docker 依赖」之上，提供一套 **自包含全栈** 可选方案：
> 后端 + Celery + PostgreSQL + Redis + MinIO + 前端（admin / portal 两个开源前端）
> 全部容器化，前端**内置 Nginx** 托管静态资源并反向代理 `/api`，开箱即用。
> （开发者门户 developer-web 为闭源模块，不在本仓库，见下表说明。）

---

## 0. 定位与隔离

- **独立 compose 文件**：`docker-compose.fullstack.yml`，不影响现有
  `docker-compose.yml`（dev）与其 `cenkor-*` 容器、也不影响宝塔托管的 `8002` 后端进程。
- **命名全隔离**：容器名/卷名统一 `cenkorfs-*` 前缀；网络名 `cenkor-admin-fullstack_*`。
- **端口独立**（默认，均可用 `.env` 覆盖）：

| 服务 | 对外端口（默认） |
|------|----------------|
| 后端 API（含 `/api/docs`） | `8001` |
| 管理后台 admin-web | `5185` |
| 门户 portal-web | `5192` |
| 开发者门户 developer-web | `5175`（**可选**，闭源模块，需 `--profile developer`） |
| PostgreSQL | `5543` |
| Redis | `6382` |
| MinIO API / 控制台 | `9006` / `9007` |

> ℹ️ **「应用中心」在开源仓库内，不在开源仓库里的是「开发者门户」。**
> 管理后台 admin-web 自带应用中心（侧边栏「系统 → 应用中心」，`/system/apps`，接口
> `/api/v1/system/apps`），可查看已装 App、安装 ZIP 包、启停应用，**默认随 `bootstrap` 部署**。
> 闭源的是 `frontend/developer-web/`（**开发者门户**，供开发者上架/管理自己的 App），
> 被 `.gitignore` 排除 → compose 里挂在 `profiles: ["developer"]` 下，**默认不构建**，
> 公开仓库 clone 下来一条命令即可跑通。在源码齐全的机器上启用：`--profile developer`。
> `scripts/bootstrap-fullstack.sh` 会自动探测该目录是否存在并决定是否带上 profile。

> 端口与宝塔 Python 项目（8000/8002/8008/8500/23789/30080/9700 等）及
> blog/bizcloud/fettle 容器端口均不冲突。

---

## 1. 准备环境变量（推荐交给脚本自动完成）

```bash
bash scripts/bootstrap-fullstack.sh
```

脚本会生成 `.env`，自动填入随机的 `POSTGRES_PASSWORD` / `MINIO_ROOT_PASSWORD` / `SECRET_KEY`
（权限 600），并把 `PUBLIC_BASE_URL`、`CORS_ORIGINS` 指向本机 IP，无需手工编辑。

**想手动指定**时：

```bash
cp docker/fullstack/env.fullstack.example .env
vim .env                      # 至少设置 POSTGRES_PASSWORD 与 MINIO_ROOT_PASSWORD
```

> ⚠️ **文件名必须是 `.env`。** `docker-compose.fullstack.yml` 里的服务写死了 `env_file: .env`，
> 而 `--env-file` 只影响 compose 文件的**变量插值**，**不会把变量注入容器**。
> 所以用 `.env.fullstack` 之类的名字，最后必然报 `env file .env not found`。
> （本文件旧版本曾这样写，已修正。）

常用覆盖项（`FS_` 前缀，缺省即用上表默认值）：

```
FS_BACKEND_PORT=8001
FS_ADMIN_WEB_PORT=5185
FS_PORTAL_WEB_PORT=5192
FS_DEVELOPER_WEB_PORT=5175
FS_POSTGRES_PORT=5543
FS_REDIS_PORT=6382
FS_MINIO_API_PORT=9006
FS_MINIO_CONSOLE_PORT=9007
```

### 构建加速：怎么换镜像源（国内 / WSL 必看）

构建镜像要下载 apt 包、pip wheel、npm 包，默认全走官方源。**海外机器这样最快**；
中国大陆直连 `pypi.org` 实测只有约 30 kB/s，光装依赖一步就要 20 分钟以上。

这三个变量写在 `.env` 里，只影响 `docker build`，不影响运行时：

| 变量 | 作用 | 默认值 | 国内可选值 |
|---|---|---|---|
| `APT_MIRROR` | Debian apt 源，**只写域名** | `deb.debian.org` | `mirrors.aliyun.com` / `mirrors.tuna.tsinghua.edu.cn` |
| `PIP_INDEX_URL` | pip 索引，**带 `https://`** | `https://pypi.org/simple` | `https://mirrors.aliyun.com/pypi/simple/` |
| `NPM_REGISTRY` | npm registry，**带 `https://`** | `https://registry.npmjs.org` | `https://registry.npmmirror.com` |

**推荐做法：让脚本选，不用手改文件。**

```bash
bash scripts/bootstrap-fullstack.sh --mirror cn        # 强制国内镜像（WSL / 大陆机器）
bash scripts/bootstrap-fullstack.sh --mirror global    # 强制官方源（海外服务器 / CI）
bash scripts/bootstrap-fullstack.sh                    # 默认 auto：探测后决定
```

`auto` 会实测官方源与三个国内镜像的**下载吞吐**，国内快 20% 以上才切换；
`cn` 把三个国内镜像全部测一遍，取**实测最快**的那个，三个都不可达才回退官方源并告警
（不会中断部署）。每个源只测一次，最多 6 秒。

> **为什么测吞吐而不是测首字节。** 首字节只证明「服务器肯不肯应答」。实测遇到过索引页
> 49 ms 就返回、真实 wheel 下载却只有 200 KB/s 的镜像 —— 按顺序取第一个可达的，正好会
> 选中最慢的那个，构建照样跑 20 分钟。所以选源依据必须是吞吐。

> `.env` 里已经有启用的 `PIP_INDEX_URL` 时，脚本会直接沿用、不再重复测速（省 10~20 秒）；
> 想重新测就显式传 `--mirror auto`。

`--mirror` 在 `.env` 已存在时同样生效：它会**就地改写**那三行，其余配置原样保留。
所以已经部署过的机器想换源，直接重跑带参数的命令即可，不用删 `.env`。
不加 `--mirror` 时脚本**不会改动**已有 `.env`，只在检测到网络偏慢时提示你加参数。

**手工改也可以**（不想用脚本时）：

```bash
cp docker/fullstack/env.fullstack.example .env    # 或直接编辑已有的 .env
vim .env                                          # 打开「构建加速」段，取消那三行注释
```

**或者只在这一次构建生效**（不改文件）：

```bash
APT_MIRROR=mirrors.aliyun.com \
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
NPM_REGISTRY=https://registry.npmmirror.com \
docker compose -f docker-compose.fullstack.yml up -d --build
```

> **换源后要重新构建才生效。** `build-arg` 变了，对应镜像层缓存自动失效，pip / npm 层会重跑。
> wheel 缓存在 BuildKit cache mount 里，同一台机器后续改业务代码不必重下。
>
**后端依赖用 uv 装，不是 pip。**

`docker/fullstack/backend.Dockerfile` 的依赖安装走 `uv pip install --system`。
原因是 pip 的下载**串行**（一个包装完才下一个），40 个直接依赖（88 个含传递依赖）
在慢网下单这一步就能跑 20 分钟；uv 默认并发下载，同样的带宽能把时间压到几分之一
—— **网络越慢，差距越大**。

海外快网实测（同一台机器、同一份 `requirements.txt`）：

| 场景 | pip | uv |
|---|---:|---:|
| 首次安装 88 个包 | 27.8s | **0.85s** |
| 改 `requirements.txt` 触发重建（缓存已热） | 25.0s | **0.94s** |

依赖结果逐包比对过：包集合与版本完全一致，零差异。uv 本体装完即卸载，不进最终镜像。

**外置 App 的依赖也会被装进镜像。**

`apps/*/requirements.txt` 由各 App 自己声明（如 `collect` 的 `parsel` /
`trafilatura` / `feedparser`），主 `requirements.txt` 刻意不含 —— 开源版没有
这些 App，装着是浪费。镜像在 `COPY backend/src` 之后会遍历安装，`apps/` 不存在
（CI 与客户 checkout）时自动跳过，所以两种构建都能成功。

自己往镜像里加 App 时，只要把目录放进 `backend/src/apps/<key>/`、清单写进
`<key>/requirements.txt`，重新 `--build` 即可，不用改 Dockerfile。

> **别指望 WSL2 走 Windows 的代理。** 它默认不继承主机代理设置，Windows 上开了代理，
> WSL 里直连 pypi.org 依然是 30 kB/s。必须换源（或在 WSL 内单独配代理）。
>
> **海外机器不要开国内源。** 实测某些海外主机访问国内镜像站直接不可达（超时），
> 会让构建失败。这类机器保持注释，或显式 `--mirror global`。

---

## 2. 一条命令启动全栈

```bash
bash scripts/bootstrap-fullstack.sh
```

> 上一节选了国内镜像的话，这条命令带上同样的参数即可（如 `--mirror cn`）：
> 它只影响镜像构建、不影响启动，带上一次就够了。

脚本内部等价于（外加 `.env` 生成、就绪等待与结果汇总）：

```bash
docker compose -f docker-compose.fullstack.yml up -d --build
```

> **不需要 `--env-file`**：`docker compose` 会自动读取当前目录的 `.env`，同时用于变量插值与
> 容器 `env_file`。**也不需要 `--project-name`**：compose 顶层已声明 `name: cenkor-admin-fullstack`，
> 且容器名/卷名固定 `cenkorfs-*` 前缀，与 dev 的 `cenkor-*` 完全隔离。
> （旧版本文档让用户传 `.env.fullstack`，会直接报 `env file .env not found`，已修正。）

首启会自动完成全部初始化，**无需任何手动 `exec`**：

| 阶段 | 由谁完成 |
|---|---|
| 拉取/构建镜像；拉起 PostgreSQL / Redis / MinIO（含健康检查） | `docker compose` |
| 数据库迁移 `alembic upgrade heads` | 容器入口 `docker/fullstack/entrypoint.sh` |
| 灌入种子数据（幂等）→ 打印管理员初始口令 | 同上 |
| 构建三个前端（各自内置 Nginx 托管 dist、反代 `/api` 到 `backend:8000`） | 镜像构建阶段 |

### 🔑 初始管理员口令怎么拿（**必读，否则登不进去**）

> **本仓库没有任何默认口令。** `admin123` / `admin@123` 之类的「常见默认密码」**一律无效** ——
> 口令在首次初始化时**随机生成**，只完整显示一次；库里只存 bcrypt 哈希，**事后推不回来**。

**① 部署时直接看终端**（`bootstrap-fullstack.sh` 收尾会打印）：

```
====================================================================
  已创建管理员：admin@cenkor.cn
  初始密码    ：xxxxxxxxxxxxxxxx
  ⚠️ 此口令只显示这一次，请立即登录并修改
====================================================================
```

**② 当时没记下来 → 翻服务端日志**：

```bash
docker compose -f docker-compose.fullstack.yml logs backend | grep -A3 已创建管理员
```

**③ 日志也没了 → 用重置脚本**（会同时递增 `token_version` 踢掉旧会话）：

```bash
bash scripts/reset-admin-password.sh                      # 随机生成并打印新口令
bash scripts/reset-admin-password.sh --password 'YourPass'  # 指定新口令
```

> ⚠️ **注意日志不是永久的**：`docker compose down`（即使不带 `-v`，数据卷保留）也会**重建容器** →
> 容器日志清空；而此刻 seed 发现管理员已存在会**跳过、不再打印** → 口令就此丢失，只能走 ③。
>
> `admin123` 是本仓库**历史上真实泄露过的默认口令**（曾被印到公网部署页上），
> 现已彻底移除；如你在别处仍看到它，那是过期资料。

**想一开始就自己定口令**：部署前写进 `.env`，`seed` 会优先取值（设了就不再随机、也不再打印）：

```bash
echo 'CENKOR_ADMIN_PASSWORD=你的口令' >> .env
bash scripts/bootstrap-fullstack.sh
```

> 需要跳过自动初始化时：`SEED_ON_STARTUP=0`（跳过种子数据）、`SKIP_MIGRATE=1`（跳过迁移）。

访问验证：

| 地址 | 期望 |
|------|------|
| `http://服务器IP:5185` | 管理后台登录页 |
| `http://服务器IP:5192` | 门户用户中心 |
| `http://服务器IP:5175` | 开发者门户（闭源模块，需 `--profile developer`） |
| `http://服务器IP:8001/api/health` | 后端健康检查 |
| `http://服务器IP:8001/api/docs` | Swagger 文档 |

> 登录后侧边栏应有「**系统 → 应用中心**」（`/system/apps`）。若缺失，执行
> `docker compose -f docker-compose.fullstack.yml exec backend python -m cenkor_admin.scripts.seed`
> 补齐菜单（seed 幂等，会给超管补挂该菜单）。

---

## 3. 常用运维命令

```bash
FS="docker compose -f docker-compose.fullstack.yml"

$FS ps                  # 查看状态
$FS logs -f backend     # 后端日志
$FS logs -f admin-web   # 某前端日志
$FS down                # 停止（保留数据卷）
$FS down -v             # 停止并清空数据卷（谨慎）
$FS up -d               # 改配置/改代码后重起（需配合 --build 重建镜像）
```

---

## 4. 离线安装包（内网 / 无外网部署）

在能联网且已成功构建的机器上：

```bash
bash docker/fullstack/export-fullstack.sh [输出目录]
# 产物：<out>/cenkor-fullstack_<时间戳>.tar.gz（含全部自有镜像 + postgres/redis/minio）
```

目标机（无外网）：

```bash
docker load < cenkor-fullstack_<时间戳>.tar.gz
# 目标机也要有 .env（把源机的 .env 拷过来，或跑一次 bootstrap 生成）
docker compose -f docker-compose.fullstack.yml up -d
```

---

## 5. 多架构构建（linux/amd64 + linux/arm64）

```bash
bash docker/fullstack/build-multiarch.sh [--push]
```

- AMD64 + ARM64 交叉构建（首次需启用 binfmt）。
- `--push` 推送 registry（去掉 `--load`）。
- 生成镜像标签 `*:fullstack-multi`，把 compose 里 `image: xxx:fullstack` 改为 `:fullstack-multi` 即可。

---

## 6. 与现有部署方式的关系

| 方式 | 命令/入口 | 适用 |
|------|-----------|------|
| **全栈容器化（本方案）** | `docker-compose.fullstack.yml` | 前后端一条命令全含，前端内置 Nginx |
| Docker 自管 nginx | `bash scripts/deploy.sh --mode docker` | 仅后端容器，nginx 宿主机托管 |
| 宝塔静态 dist | `scripts/deploy-baota-static.sh` | 宝塔托管前端 dist 的静态方案 |
| 裸机 systemd | `scripts/install-native.sh` | 全裸机、无 Docker |

本方案与「宝塔静态 dist」二选一即可，两者都会产出前端静态产物；差异在托管与反代方式。

在此目录下：
- `docker/fullstack/backend.Dockerfile` —— 后端生产镜像
- `docker/fullstack/entrypoint.sh` —— 后端容器入口（自动迁移 + 幂等灌种子数据）
- `docker/fullstack/frontend.Dockerfile` —— 前端镜像（`--build-arg FRONTEND=admin-web|portal-web|developer-web`）
- `docker/fullstack/nginx-app.conf` —— 前端内置 Nginx（托管 + `/api` 反代 + WebSocket）