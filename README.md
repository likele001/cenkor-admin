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

## 快速启动（开发）

> 仅用于**本地开发机**（后端 `--reload` 热重载 + 前端 dev server）。**部署到公网请看下面的「生产部署（核心）」。**

```bash
cp .env.example .env
docker compose up -d
```

- 管理后台：http://localhost:5173
- 用户中心：http://localhost:5175（`npm run dev:portal`）
- API：http://localhost:8000/api/docs
- 默认账号：`admin@cenkor.cn` / `admin123`

> 后端启动时 lifespan 会自动执行 `alembic upgrade head` 建表，**无需手动跑迁移**。
> seed 数据经 `docker compose exec backend python -m cenkor_admin.scripts.seed` 生成。

> ⚠️ **安全提示（务必阅读）**
>
> 上面的账号是初始化种子数据里的默认管理员，密码以明文写在文档中。
> **任何部署到公网之前，必须先做三件事：**
> 1. 立即修改默认管理员密码
> 2. 修改 `.env` 中的 `SECRET_KEY`（不要用仓库示例里的占位值）
> 3. 删除或禁用不需要的种子账号
>
> 否则任何人都可以用 `admin@cenkor.cn` / `admin123` 直接登录你的后台。

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

**可选部署模式**（交付给别人 / 换环境，本机生产未采用）：

```bash
cp .env.example .env        # 按需修改 .env 里的密码/端口
docker compose -f docker-compose.fullstack.yml --project-name cenkor-admin-fullstack up -d --build
```

- 后端 API：http://服务器IP:8001/api/health → `/api/docs`
- 管理后台：http://服务器IP:5185
- 门户：http://服务器IP:5192 · 开发者门户：http://服务器IP:5175

> 首次部署会自动完成数据库迁移与建表（后端 lifespan 自动 `alembic upgrade head`）。
> 播种种子数据：`docker compose -f docker-compose.fullstack.yml --project-name cenkor-admin-fullstack exec backend python -m cenkor_admin.scripts.seed`
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