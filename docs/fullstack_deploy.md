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
> 后端 + Celery + PostgreSQL + Redis + MinIO + 三个前端（admin / portal / developer）
> 全部容器化，前端**内置 Nginx** 托管静态资源并反向代理 `/api`，开箱即用。

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
| 开发者门户 developer-web | `5175` |
| PostgreSQL | `5543` |
| Redis | `6382` |
| MinIO API / 控制台 | `9006` / `9007` |

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

---

## 2. 一条命令启动全栈

```bash
bash scripts/bootstrap-fullstack.sh
```

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
| 数据库迁移 `alembic upgrade head` | 容器入口 `docker/fullstack/entrypoint.sh` |
| 灌入种子数据（幂等）→ 打印管理员初始口令 | 同上 |
| 构建三个前端（各自内置 Nginx 托管 dist、反代 `/api` 到 `backend:8000`） | 镜像构建阶段 |

管理员初始口令打印在服务端日志中：

```bash
docker compose -f docker-compose.fullstack.yml logs backend | grep -A3 已创建管理员
```

> 需要跳过自动初始化时：`SEED_ON_STARTUP=0`（跳过种子数据）、`SKIP_MIGRATE=1`（跳过迁移）。

访问验证：

| 地址 | 期望 |
|------|------|
| `http://服务器IP:5185` | 管理后台登录页 |
| `http://服务器IP:5192` | 门户用户中心 |
| `http://服务器IP:5175` | 开发者门户 |
| `http://服务器IP:8001/api/health` | 后端健康检查 |
| `http://服务器IP:8001/api/docs` | Swagger 文档 |

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