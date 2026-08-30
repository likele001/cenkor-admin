# Cenkor Admin Platform · Monorepo

**核心平台**：FastAPI 后端 + 管理后台 + 用户中心，可独立部署，**不依赖官网**。

| 项 | 值 |
|----|---|
| **类型** | Docker Compose / 宝塔静态 dist / 裸机 systemd |
| **服务** | PostgreSQL 16 + Redis 7 + MinIO + Backend + Admin-Web + Portal-Web |
| **前端** | Vue 3 + Vite + Tailwind |
| **后端** | Python 3.11 + FastAPI + SQLAlchemy 2.0 async |

📖 **文档索引**：[`docs/INDEX.md`](docs/INDEX.md)  
📦 **打包交付**：[`docs/PACKAGING.md`](docs/PACKAGING.md)

## 快速启动（开发）

```bash
cp .env.example .env
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec backend python -m cenkor_admin.scripts.seed
```

- 管理后台：http://localhost:5173
- 用户中心：http://localhost:5175（`npm run dev:portal`）
- API：http://localhost:8000/api/docs
- 默认账号：`admin@cenkor.cn` / `admin123`

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


| 模式 | 命令 | 文档 |
|------|------|------|
| **宝塔静态 dist（推荐）** | `bash scripts/deploy.sh --mode baota-static` | [`docs/BAOTA_STATIC_DEPLOY.md`](docs/BAOTA_STATIC_DEPLOY.md) |
| Docker 自管 nginx | `bash scripts/deploy.sh --mode docker` | [`docker-compose.prod.yml`](docker-compose.prod.yml) |
| 宝塔反代 Docker 前端 | `bash scripts/deploy.sh --mode baota` | [`docs/DOMAIN_SETUP.md`](docs/DOMAIN_SETUP.md) |
| 裸机 systemd | `sudo bash scripts/install-native.sh` | [`docs/NATIVE_DEPLOY.md`](docs/NATIVE_DEPLOY.md) |

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

详见 [`docs/PACKAGING.md`](docs/PACKAGING.md)、[`docs/release/`](docs/release/)。

## 可选扩展

- 外部官网 CMS：[`docs/addons/WEBSITE_CMS.md`](docs/addons/WEBSITE_CMS.md) · [`deploy/addons/`](deploy/addons/)

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
