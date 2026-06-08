# Cenkor Admin · 裸机部署（systemd + 宝塔反代）

适用场景：不使用 Docker，在宿主机直接运行 Python/Node，由宝塔 nginx 做 SSL 与反代。

## 前置依赖

- Python 3.11+
- Node.js 20+
- PostgreSQL 16（宝塔软件商店或系统包）
- Redis 7
- MinIO（建议仍用 Docker 单容器：`docker run -p 9000:9000 minio/minio server /data`）

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
