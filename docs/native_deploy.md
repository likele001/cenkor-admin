# Cenkor Admin · 裸机部署（systemd + 宝塔反代）

> ℹ️ **本机生产未采用本文方案。**
>
> 本机生产由**宝塔「Python 项目」**托管后端（用户 `www`，端口 `8002`），
> 不是 systemd 单元。权威文档见 [`deploy.md`](deploy.md)。
> 本文仅在「不用宝塔守护、改用 systemd」时参考。


适用场景：不使用 Docker，在宿主机直接运行 Python/Node，由宝塔 nginx 做 SSL 与反代。

## 前置依赖

- Python 3.11+
- Node.js 20+
- PostgreSQL 16（宝塔软件商店或系统包）
- Redis 7
- MinIO（本机为 systemd 托管的原生服务，数据目录 `/var/minio/data`）
  ⚠️ 官方下载站 `dl.min.io` 已返回 **410**，`wget dl.min.io/...` 那套教程已失效；
  安装步骤（GitHub Release 的 `.deb` / 裸二进制 + systemd 单元）见
  [`deploy.md` §5.3](deploy.md#53-minio本地对象存储--双写备份) 的「安装 MinIO（宿主机）」

## 步骤

```bash
# 1. 生成生产配置
bash scripts/gen-secrets.sh

# 2. 编辑 .env.prod：DATABASE_URL / REDIS_URL 指向宿主机服务
#    例：DATABASE_URL=postgresql+asyncpg://cenkor:xxx@127.0.0.1:5432/cenkor

# 3. 一键安装（需 root）
sudo bash scripts/install-native.sh

# 或仅启用后端 systemd（Docker 跑 PG/Redis，backend 裸进程）：
sudo cp deploy/systemd/cenkor-backend.service /etc/systemd/system/
sudo cp deploy/examples/env.host.override /etc/cenkor/env.host.override
# 编辑 /etc/cenkor/env.host.override 填入 DATABASE_URL / REDIS_URL
sudo systemctl daemon-reload
sudo systemctl enable --now cenkor-backend

# 日常重启（无 systemd 时）：
bash scripts/restart-backend-host.sh

# 4. 宝塔反代（与 Docker 模式相同）
#    api.cenkor.cn  → 127.0.0.1:8002
#    admin.cenkor.cn → 127.0.0.1:5174
#    portal.cenkor.cn → 127.0.0.1:5175
```

参考配置片段：[`deploy/baota/reverse-proxy.conf`](../deploy/baota/reverse-proxy.conf)

## 🔑 初始管理员口令怎么拿（**必读**）

> **本仓库没有任何默认口令** —— 管理员口令在首次灌种子数据时**随机生成**，
> 库里只存 bcrypt 哈希，**事后推不回来**。`admin123` 之类的是本仓库历史上泄露过、现已移除的口令。

**① 灌种子时直接看终端**（`scripts/migrate-and-seed-host.sh` / `seed.py` 会打印）：

```
  已创建管理员：admin@cenkor.cn
  初始密码    ：xxxxxxxxxxxxxxxx
```

**② 没记下来 → 重置**（本脚本会自动识别「宿主机 venv」模式，无需进容器）：

```bash
bash scripts/reset-admin-password.sh                        # 随机生成并打印新口令
bash scripts/reset-admin-password.sh --password '你的新口令'  # 指定新口令
```

> **想一开始就自己定**：灌种子前在 `.env`（或宝塔项目的环境变量）里设置
> `CENKOR_ADMIN_PASSWORD=你的口令` —— 设了就不再随机、也不再打印。
>
> ⚠️ 注意配置优先级：**宝塔面板「环境变量」> `.env` > 代码默认值**。
> 宝塔 Python 项目的 `env_list` 只有 7 条且不含本项，所以写到 `backend/.env` 即可生效。

## systemd 服务

| Unit | 说明 |
|------|------|
| `cenkor-backend.service` | FastAPI uvicorn |
| `cenkor-celery.service` | Celery worker |
| `cenkor-admin-web.service` | 管理后台静态 |
| `cenkor-portal-web.service` | 用户中心静态 |

```bash
systemctl status cenkor-backend
journalctl -u cenkor-backend -f
```

## 备份

```bash
bash scripts/backup.sh
```

## 与 Docker 模式对比

| 项 | Docker | 裸机 systemd |
|----|--------|-------------|
| 隔离性 | 好 | 一般 |
| 运维复杂度 | 中 | 低（熟悉宝塔时） |
| 升级 | compose pull/build | pip/npm + restart |
| 推荐 | 多环境一致 | 单机宝塔已有 PG/Redis |
