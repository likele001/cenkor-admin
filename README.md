# Cenkor Admin Platform · Monorepo

**核心平台**：FastAPI 后端 + 管理后台 + 用户中心，可独立部署，**不依赖官网**。

| 项 | 值 |
|----|---|
| **类型** | 宿主机 + 宝塔托管（Docker Compose 为**可选交付路径**） |
| **服务** | 宝塔 Python 项目 + 宿主机 PostgreSQL 16 / Redis 7 / MinIO + 宝塔 nginx 静态 dist |
| **前端** | Vue 3 + Vite + Tailwind |
| **后端** | Python 3.11 + FastAPI + SQLAlchemy 2.0 async |

📖 **文档索引**：[`docs/index.md`](docs/index.md)
📦 **打包交付**：[`docs/packaging.md`](docs/packaging.md)

## 一键部署（Docker，推荐）

> 后端 + Celery + PostgreSQL + Redis + MinIO + 三个前端全部容器化，前端内置 Nginx。
> **不需要预先安装任何中间件**，一台装了 Docker 的干净机器即可。

```bash
git clone https://github.com/likele001/cenkor-admin.git
cd cenkor-admin
bash scripts/bootstrap-fullstack.sh
```

脚本会自动完成全部步骤，中途无需干预：

1. 生成 `.env`（随机填充 `POSTGRES_PASSWORD` / `MINIO_ROOT_PASSWORD` / `SECRET_KEY`，权限 600）
2. `docker compose up -d --build` 拉起全部容器
3. 容器启动时自动执行数据库迁移并灌入种子数据（幂等）
4. 等待后端就绪，**在屏幕上打印访问地址和初始管理员口令**

部署完成后的地址（`<IP>` 为部署机 IP）：

| 地址 | 说明 |
|---|---|
| `http://<IP>:5185` | 管理后台 |
| `http://<IP>:5192` | 用户中心 |
| `http://<IP>:8001/api/docs` | API 文档 / Swagger |
| `http://<IP>:8001/api/health` | 健康检查 |

> **开发者门户（应用中心）不在本开源仓库中**（闭源模块，见 `.gitignore` 的
> `frontend/developer-web/`），因此默认不部署。在源码齐全的机器上加
> `--profile developer` 即可启用（默认端口 `5175`）。

管理员账号为 `admin@cenkor.cn`。**初始口令是随机生成的，只在首次启动时打印一次**
（`docker compose -f docker-compose.fullstack.yml logs backend`），请登录后立即修改。

> 端口全部可用 `.env` 里的 `FS_*` 变量覆盖。完整说明见
> [`docs/fullstack_deploy.md`](docs/fullstack_deploy.md)。

## 快速启动（开发）

> 仅用于**本地开发机**（后端 `--reload` 热重载 + 前端 dev server）。**部署到公网请看下面的「生产部署（核心）」。**

```bash
cp .env.example .env
docker compose up -d
```

- 管理后台：http://localhost:5173
- 用户中心：http://localhost:5175（`npm run dev:portal`）
- API：http://localhost:8000/api/docs
- 管理员账号：`admin@cenkor.cn`（**初始口令随机生成，不写死在源码与文档里**）

> 后端启动时 lifespan 会自动执行 `alembic upgrade head` 建表，**无需手动跑迁移**。
> 种子数据经 `docker compose exec backend python -m cenkor_admin.scripts.seed` 生成；
> 未设置环境变量 `CENKOR_ADMIN_PASSWORD` 时会生成随机口令并**只打印一次**。

> ⚠️ **安全提示（务必阅读）**
>
> 本仓库**不包含任何默认口令**，每个实例的管理员口令都在首次初始化时随机生成。
> **部署到公网之前，必须先做两件事：**
> 1. 用随机生成的初始口令登录，并立即在后台改成自己的口令
> 2. 确认 `.env` 里的 `SECRET_KEY` 是随机值（不要用 `.env.example` 里的占位值）
>
> 这两步在 `bash scripts/bootstrap-fullstack.sh` 部署流程里已自动完成。

## 生产部署（核心）

> 部署到公网前，请先完成上文「安全提示」中的三件事（改默认密码、换 `SECRET_KEY`、
> 清理种子账号），并确认 `.env` 未被提交进版本库。

**本机生产环境是「宿主机 + 宝塔」，不使用 Docker：**

| 组件 | 位置 | 端口 |
|---|---|---|
| 后端 FastAPI | 宝塔 Python 项目 `cenkor`（用户 `www`） | `8002` |
| PostgreSQL | 宿主机原生 | `5432` |
| Redis | 宿主机原生 | `6379` / `db5` |
| MinIO | 宿主机原生（systemd） | `9000` |
| 前端 | 宝塔 nginx 直接 serve `frontend/*/dist` | — |

📖 **完整流程 / 端口台账 / 配置优先级 / 验证清单 / 回滚与排障 → [`docs/deploy.md`](docs/deploy.md)**

```bash
bash scripts/build-frontends.sh    # 构建前端 dist（宝塔直接 serve，构建完即生效）
# 后端改动后：在宝塔面板 → 网站 → Python 项目 → cenkor → 重启
```

**可选部署模式**（交付给别人 / 换环境，本机未采用）：

```bash
bash scripts/bootstrap-fullstack.sh     # 见上方「一键部署（Docker）」
```

- 后端 API：http://服务器IP:8001/api/health → `/api/docs`
- 管理后台：http://服务器IP:5185
- 门户：http://服务器IP:5192
- 开发者门户：http://服务器IP:5175（可选，需 `--profile developer` 且源码齐全）

> 首次部署自动完成：生成 `.env`（随机密钥）→ 数据库迁移建表 → 灌入种子数据 → 打印访问地址与初始口令。
> 以上全部由容器入口脚本 `docker/fullstack/entrypoint.sh` 完成，**不再需要手动 `exec` 两条命令**。
> 完整说明见 [`docs/fullstack_deploy.md`](docs/fullstack_deploy.md)。

其他部署模式：

| 模式 | 命令 | 文档 |
|------|------|------|
| Docker 全栈（交付演示） | `bash scripts/deploy.sh --mode docker` | [`docs/fullstack_deploy.md`](docs/fullstack_deploy.md) |
| 宝塔静态 dist + Docker 中间件 | `bash scripts/deploy.sh --mode baota-static` | [`docs/baota_static_deploy.md`](docs/baota_static_deploy.md) |
| 裸机 systemd | `sudo bash scripts/install-native.sh` | [`docs/native_deploy.md`](docs/native_deploy.md) |

```bash
bash scripts/gen-secrets.sh          # 通用域名占位符
bash scripts/deploy-baota-static.sh    # 构建 dist + 起后端
```

## 模块

- **admin-web** — CMS / RBAC / 应用中心 / 审计
- **portal-web** — 注册 / 登录 / 资料
- **backend** — FastAPI + Celery + 公开 CMS API（`/api/v1/public/*`）

## 打包交付

```bash
bash scripts/package-core.sh    # → release/cenkor-admin-core-*.tar.gz
```

详见 [`docs/packaging.md`](docs/packaging.md)、[`docs/release/`](docs/release/)。

## 可选扩展

- 外部官网 CMS：[`docs/addons/website_cms.md`](docs/addons/website_cms.md) · [`deploy/addons/`](deploy/addons/)

## 数据库

- 生产默认 **PostgreSQL 16**
- 兼容 **MySQL 5.7+**（CI 双库验证）

## 备份

```bash
bash scripts/backup.sh
```

## 开源许可

本项目基于 [MIT License](LICENSE) 开源，版权归 **李可乐** 所有（© 2026）。

你可以自由地使用、复制、修改、合并、发布、分发、再许可及销售本软件，
**包括用于商业目的**，唯一条件是保留上述版权声明与许可声明。

本软件按「原样」提供，不作任何明示或暗示的担保，详见 [LICENSE](LICENSE)。