# Cenkor Admin · 全栈容器化部署（含前端，一条命令）

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

## 1. 准备环境变量

```bash
# 从现有 dev 的 .env 读取数据库/密钥/S3 配置（变量名兼容），可直接复用：
cp .env .env.fullstack        # 或按模板逐个填
cp docker/fullstack/env.fullstack.example .env.fullstack

# 编辑至少设置这两项（其余用默认即可）：
#   POSTGRES_PASSWORD=
#   MINIO_ROOT_PASSWORD=
vim .env.fullstack
```

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
docker compose -f docker-compose.fullstack.yml \
  --project-name cenkor-admin-fullstack \
  --env-file .env.fullstack \
  up -d --build
```

> **必须显式 `--project-name`**：本机 `.env` 里 `COMPOSE_PROJECT_NAME=cenkor-admin`
> 会覆盖 compose 顶层的 `name:`，导致默认网络沿用 dev 前缀。显式指定后网络名也独立。
> （即使漏加，容器/卷名的 `cenkorfs-*` 固定前缀也保证不会撞车。）

首启会自动：拉取/构建镜像 → 起 PostgreSQL/Redis/MinIO（含健康检查）→ 启动后端与 Celery →
构建并启动三个前端（各内置 Nginx 托管 dist 并反代 `/api` 到 `backend:8000`）。

首次需先初始化数据库与种子数据：

```bash
docker compose -f docker-compose.fullstack.yml \
  --project-name cenkor-admin-fullstack \
  --env-file .env.fullstack \
  exec backend alembic upgrade head
docker compose -f docker-compose.fullstack.yml \
  --project-name cenkor-admin-fullstack \
  --env-file .env.fullstack \
  exec backend python -m cenkor_admin.scripts.seed
```

> 若后端使用了 `DB_AUTO_CREATE`/`DB_AUTO_SEED` 之类自建表机制，则无需手动 alembic，
> 视实际入口脚本而定。

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
FS="docker compose -f docker-compose.fullstack.yml --project-name cenkor-admin-fullstack --env-file .env.fullstack"

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
docker compose -f docker-compose.fullstack.yml \
  --project-name cenkor-admin-fullstack \
  --env-file .env.fullstack \
  up -d
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
- `docker/fullstack/frontend.Dockerfile` —— 前端镜像（`--build-arg FRONTEND=admin-web|portal-web|developer-web`）
- `docker/fullstack/nginx-app.conf` —— 前端内置 Nginx（托管 + `/api` 反代 + WebSocket）