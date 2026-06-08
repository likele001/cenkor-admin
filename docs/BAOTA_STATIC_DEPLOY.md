# Cenkor Admin · 宝塔面板完整部署指南

> **推荐部署模式（与 lightmes 相同）**  
> 前端：`npm run build` → 宝塔站点根目录指向 `dist`（纯静态）  
> 后端：FastAPI 监听 `127.0.0.1:8002`，宝塔 **只反代 `/api/`**  
> 中间件：PostgreSQL / Redis / MinIO 用 Docker 跑，映射到本机端口  

相关文档：[`CORE_PLATFORM.md`](CORE_PLATFORM.md) · [`addons/WEBSITE_CMS.md`](addons/WEBSITE_CMS.md)（可选官网）

---

## 目录

1. [架构总览](#一架构总览)
2. [域名与端口规划](#二域名与端口规划)
3. [前置条件](#三前置条件)
4. [第一步：获取代码与生成密钥](#四第一步获取代码与生成密钥)
5. [第二步：Docker 中间件](#五第二步docker-中间件)
6. [第三步：后端（二选一）](#六第三步后端二选一)
7. [第四步：构建前端 dist](#七第四步构建前端-dist)
8. [第五步：宝塔建站 — 管理后台](#八第五步宝塔建站--管理后台)
9. [第六步：宝塔建站 — 用户中心](#九第六步宝塔建站--用户中心)
10. [第七步：SSL 证书](#十第七步ssl-证书)
11. [第八步：飞书 OAuth（可选）](#十一第八步飞书-oauth可选)
12. [第九步：验收清单](#十二第九步验收清单)
13. [日常发布与运维](#十三日常发布与运维)
14. [常见问题](#十四常见问题)

---

## 一、架构总览

```
                    ┌─────────────────────────────────────────┐
                    │           宝塔 Nginx（80/443）            │
                    └─────────────────────────────────────────┘
                      │                    │                │
          admin.cenkor.cn          portal.cenkor.cn    www.cenkor.cn
          根目录=admin dist         根目录=portal dist   官网（可选扩展）
          /api/ ─────────┐          /api/ ─────────┐
                         │                          │
                         └──────────┬───────────────┘
                                    ▼
                         127.0.0.1:8002  FastAPI (uvicorn)
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
        cenkor-postgres       cenkor-redis          cenkor-minio
        127.0.0.1:5433        127.0.0.1:6380        127.0.0.1:9002
        (Docker)              (Docker)              (Docker)
```

**和 lightmes 的对应关系：**

| lightmes | cenkor-admin |
|----------|--------------|
| `frontend-admin-pro/dist` | `frontend/admin-web/dist` |
| `frontend-portal/dist` | `frontend/portal-web/dist` |
| `admin.xxx.net` | `admin.cenkor.cn` |
| `register.xxx.net` | `portal.cenkor.cn` |
| 后端 `127.0.0.1:8000` | 后端 `127.0.0.1:8002` |
| 宝塔 Python 项目 `lightmes` | 宝塔 Python 项目 `cenkor-admin`（可选） |

**三条铁律（最容易配错）：**

1. 前端站点根目录必须是 **`dist`**，类型选 **纯静态**，关闭 PHP  
2. **只**把 `/api/` 反代到 `8002`，**不要**整站 `location /` 反代后端  
3. 伪静态用 `if + rewrite` 做 SPA 回退，**不要**在伪静态里写 `location /`（会和主配置冲突）

---

## 二、域名与端口规划

以 `cenkor.cn` 为例（请替换为你的实际域名）：

| 用途 | 域名 | 宝塔类型 | 根目录 / 反代 |
|------|------|----------|---------------|
| 管理后台 | `admin.cenkor.cn` | 纯静态网站 | `…/frontend/admin-web/dist` |
| 用户中心 | `portal.cenkor.cn` | 纯静态网站 | `…/frontend/portal-web/dist` |
| 官网（可选） | `www.cenkor.cn` | 纯静态网站 | `/www/wwwroot/website` |
| API 独立子域（可选） | `api.cenkor.cn` | 反向代理 | → `127.0.0.1:8002` |

**本机端口（仅 127.0.0.1 监听，不对外暴露）：**

| 服务 | 端口 | 说明 |
|------|------|------|
| FastAPI 后端 | **8002** | admin/portal 反代目标 |
| PostgreSQL | 5433 | Docker 映射 |
| Redis | 6380 | Docker 映射 |
| MinIO API | 9002 | 媒体存储 |
| MinIO 控制台 | 9003 | 可选，管理 bucket |

---

## 三、前置条件

### 3.1 服务器软件

| 软件 | 版本建议 | 用途 |
|------|----------|------|
| 宝塔 Linux 面板 | 7.x+ | Nginx、SSL、站点管理 |
| Docker + Docker Compose | 最新稳定版 | PG / Redis / MinIO /（可选）Backend |
| Node.js | **20+** | 构建前端 |
| Python | **3.11+** | 后端（宝塔 Python 项目或脚本） |
| Git | 任意 | 拉代码 |

宝塔面板需已安装：**Nginx**、**Docker 管理器**（或命令行 docker）、**Python 项目管理器**（若用方案 B）。

### 3.2 目录约定

```bash
/www/wwwroot/cenkor-admin/     # 本项目（核心平台）
/www/wwwroot/website/          # 可选：官网静态站（非核心包）
```

### 3.3 DNS

在域名服务商处添加 A 记录，全部指向服务器公网 IP：

```
admin.cenkor.cn   →  YOUR_SERVER_IP
portal.cenkor.cn  →  YOUR_SERVER_IP
www.cenkor.cn     →  YOUR_SERVER_IP   # 可选
api.cenkor.cn     →  YOUR_SERVER_IP   # 可选
```

---

## 四、第一步：获取代码与生成密钥

```bash
cd /www/wwwroot
# git clone <你的仓库地址> cenkor-admin   # 或上传解压
cd cenkor-admin

# 生成 .env.prod（强密码 + JWT secret，勿提交 git）
bash scripts/gen-secrets.sh
```

生成后编辑 `.env.prod`，至少填写：

```bash
# 改成你的实际域名（逗号分隔，含 https）
CORS_ORIGINS=https://admin.cenkor.cn,https://portal.cenkor.cn
FEISHU_REDIRECT_URI=https://admin.cenkor.cn/auth/feishu/callback

# 飞书（不用可留空）
FEISHU_APP_ID=
FEISHU_APP_SECRET=
```

**重要：** `.env.prod` 里默认 `DATABASE_URL` / `REDIS_URL` 使用 Docker 内网主机名（`postgres`、`redis`），**仅 Docker 跑 backend 时有效**。若用宝塔 Python 项目，见 [6.2 方案 B](#62-方案-b宝塔-python-项目推荐与-lightmes-一致)。

---

## 五、第二步：Docker 中间件

### 5.1 启动 PG + Redis + MinIO（+ 可选 Backend）

**方式 1 — 一键脚本（推荐首次部署）：**

```bash
cd /www/wwwroot/cenkor-admin
bash scripts/deploy-baota-static.sh
```

脚本会：构建前端 dist → 启动 Docker 栈 → 跑迁移 + seed → 健康检查。

**方式 2 — 手动分步：**

```bash
cd /www/wwwroot/cenkor-admin

# 仅中间件 + 后端容器
docker compose -f docker-compose.baota-static.yml --env-file .env.prod up -d

# 迁移 + 初始数据
docker compose -f docker-compose.baota-static.yml exec -T backend alembic upgrade head
docker compose -f docker-compose.baota-static.yml exec -T backend python -m cenkor_admin.scripts.seed
```

### 5.2 确认容器正常

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep cenkor
```

期望看到：

```
cenkor-postgres   ...   127.0.0.1:5433->5432/tcp
cenkor-redis      ...   127.0.0.1:6380->6379/tcp
cenkor-minio      ...   127.0.0.1:9002->9000/tcp, 127.0.0.1:9003->9001/tcp
cenkor-backend    ...   127.0.0.1:8002->8000/tcp    # 方案 A 才有
```

```bash
curl -s http://127.0.0.1:8002/api/health
# {"status":"ok",...}
```

### 5.3 默认登录账号

| 字段 | 值 |
|------|-----|
| 邮箱 | `admin@cenkor.cn` |
| 密码 | `admin123` |

**上线后请立即修改密码。**

---

## 六、第三步：后端（二选一）

后端是 **Python FastAPI**，但可以用不同方式运行。选一种即可，**不要同时占用 8002**。

### 6.1 方案 A：Docker 跑 Backend（省心）

- backend 在 Docker 容器 `cenkor-backend` 里  
- 宝塔 **Python 项目列表里看不到**（正常，它在 Docker 里）  
- 使用 `deploy-baota-static.sh` 或第五节命令即可  

**日常重启：**

```bash
docker compose -f docker-compose.baota-static.yml --env-file .env.prod restart backend celery-worker
```

**更新代码后：**

```bash
docker compose -f docker-compose.baota-static.yml --env-file .env.prod up -d --build backend
docker compose -f docker-compose.baota-static.yml exec -T backend alembic upgrade head
```

---

### 6.2 方案 B：宝塔 Python 项目（推荐，与 lightmes 一致）

和截图里的 `lightmes` 一样，在 **网站 → Python 项目 → 添加项目**，便于在面板里启停、看日志。

#### 6.2.1 先停掉 Docker backend（避免占 8002）

```bash
docker compose -f docker-compose.baota-static.yml --env-file .env.prod stop backend
# 保留 postgres / redis / minio / celery 继续运行
```

#### 6.2.2 安装 Python 依赖

```bash
cd /www/wwwroot/cenkor-admin/backend
pip3 install -e .    # 或宝塔 Python 环境管理器里选 3.11+ 再 pip install
```

#### 6.2.3 宝塔添加 Python 项目

打开 **网站 → Python 项目 → 添加项目**，填写：

| 字段 | 值 |
|------|-----|
| 项目名称 | `cenkor-admin` |
| 项目路径 | `/www/wwwroot/cenkor-admin/backend` |
| 启动方式 | **命令行启动** |
| 启动命令 | 见下方 |
| 端口 | `8002` |
| 运行用户 | `root` 或 `www`（与目录权限一致） |

**启动命令：**

```bash
python3 -m uvicorn cenkor_admin.main:app --host 127.0.0.1 --port 8002 --workers 2
```

#### 6.2.4 环境变量（关键）

在 Python 项目的「环境变量」或「配置文件」中添加（密码用 `gen-secrets.sh` 生成的，或 `docker inspect cenkor-postgres` 查看）：

```bash
PYTHONPATH=/www/wwwroot/cenkor-admin/backend/src
APP_ENV=production

# 数据库（连 Docker 映射端口，不是 postgres:5432）
DATABASE_URL=postgresql+asyncpg://cenkor:你的PG密码@127.0.0.1:5433/cenkor
DATABASE_URL_SYNC=postgresql://cenkor:你的PG密码@127.0.0.1:5433/cenkor

# Redis（若 compose 启用了 requirepass，需带密码）
REDIS_URL=redis://:你的Redis密码@127.0.0.1:6380/0
# 若 Redis 无密码：REDIS_URL=redis://127.0.0.1:6380/0

# MinIO
S3_ENDPOINT=http://127.0.0.1:9002
S3_ACCESS_KEY=minio
S3_SECRET_KEY=你的MinIO密码

# 从 .env.prod 复制
SECRET_KEY=...
CORS_ORIGINS=https://admin.cenkor.cn,https://portal.cenkor.cn
```

也可复制模板：[`deploy/examples/env.host.override`](../deploy/examples/env.host.override)

#### 6.2.5 迁移（首次 / 升级）

```bash
bash /www/wwwroot/cenkor-admin/scripts/migrate-and-seed-host.sh
```

#### 6.2.6 不用面板时的重启脚本

```bash
bash /www/wwwroot/cenkor-admin/scripts/restart-backend-host.sh
```

脚本会自动从 Docker 容器读取 PG/MinIO 真实密码，并检测 Redis 是否需 AUTH。

---

### 6.3 方案对比

| | 方案 A Docker Backend | 方案 B 宝塔 Python |
|--|----------------------|-------------------|
| 面板可见性 | Docker 容器列表 | Python 项目列表 ✅ |
| 环境变量 | `.env.prod` 内网地址 | 需改 `127.0.0.1:端口` |
| 适合 | 快速一键 | 与 lightmes 运维习惯一致 |
| 端口 | 8002 | 8002 |

---

## 七、第四步：构建前端 dist

```bash
cd /www/wwwroot/cenkor-admin

# 同域反代 /api/（推荐，VITE 留空）
bash scripts/build-frontends.sh

# 若 API 独立子域 api.cenkor.cn：
# VITE_API_BASE_URL=https://api.cenkor.cn bash scripts/build-frontends.sh
```

产物路径：

```
frontend/admin-web/dist/    → admin 站点根目录
frontend/portal-web/dist/   → portal 站点根目录
```

每次改前端代码后重新执行上述命令，**无需重启 Nginx**（刷新浏览器即可，建议 Ctrl+F5）。

---

## 八、第五步：宝塔建站 — 管理后台

### 8.1 添加站点

**网站 → 添加站点：**

| 字段 | 值 |
|------|-----|
| 域名 | `admin.cenkor.cn` |
| 根目录 | `/www/wwwroot/cenkor-admin/frontend/admin-web/dist` |
| FTP / 数据库 | 不创建 |
| PHP | **纯静态** 或 **关闭 PHP** |

### 8.2 配置伪静态（SPA 路由）

**网站 → admin.cenkor.cn → 设置 → 伪静态**

粘贴 [`deploy/baota/rewrite-admin.conf`](../deploy/baota/rewrite-admin.conf) 全部内容：

```nginx
set $spa_fallback 0;
if ($uri !~ ^/api/) {
    set $spa_fallback 1;
}
if (!-e $request_filename) {
    set $spa_fallback "${spa_fallback}1";
}
if ($spa_fallback = 11) {
    rewrite ^ /index.html last;
}
```

### 8.3 配置 API 反代

**网站 → admin.cenkor.cn → 设置 → 配置文件**

在 `server { ... }` 内、已有 `location` 块之外，**追加** [`deploy/baota/server-snippet-admin-api.conf`](../deploy/baota/server-snippet-admin-api.conf)：

```nginx
location /api/ {
    client_max_body_size 50m;
    proxy_pass http://127.0.0.1:8002/api/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

保存后 **重载 Nginx**。

### 8.4 验证 admin

```bash
curl -I https://admin.cenkor.cn/
curl -s https://admin.cenkor.cn/api/health
```

浏览器打开 `https://admin.cenkor.cn/login`，用默认账号登录。

---

## 九、第六步：宝塔建站 — 用户中心

与 admin 完全对称，仅路径不同。

| 字段 | 值 |
|------|-----|
| 域名 | `portal.cenkor.cn` |
| 根目录 | `/www/wwwroot/cenkor-admin/frontend/portal-web/dist` |
| 伪静态 | [`deploy/baota/rewrite-portal.conf`](../deploy/baota/rewrite-portal.conf) |
| API 反代 | [`deploy/baota/server-snippet-portal-api.conf`](../deploy/baota/server-snippet-portal-api.conf) |

验证：`https://portal.cenkor.cn/` 可打开注册/登录页。

---

## 十、第七步：SSL 证书

对每个站点：**网站 → 域名 → SSL → Let's Encrypt → 申请**。

勾选「强制 HTTPS」。确保 `CORS_ORIGINS` 和前端构建使用的是 `https://` 域名。

---

## 十一、第八步：飞书 OAuth（可选）

1. 飞书开放平台创建应用，拿到 `APP_ID` / `APP_SECRET`  
2. 回调地址填：`https://admin.cenkor.cn/auth/feishu/callback`  
3. 写入 `.env.prod` 或宝塔 Python 项目环境变量  
4. 重启 backend  

---

## 十二、第九步：验收清单

按顺序勾选：

- [ ] `docker ps | grep cenkor` — postgres / redis / minio 均为 Up  
- [ ] `curl http://127.0.0.1:8002/api/health` — 返回 `"status":"ok"`  
- [ ] `curl http://127.0.0.1:8002/api/v1/public/site` — 返回 JSON  
- [ ] `https://admin.cenkor.cn/login` — 页面正常，能登录  
- [ ] `https://admin.cenkor.cn/cms/products` — 登录后可进 CMS  
- [ ] `https://portal.cenkor.cn/` — 用户中心可访问  
- [ ] 浏览器 F12 → Network：API 请求走 `/api/v1/...`，非 8002 直连  
- [ ] 刷新 admin 子路由（如 `/system/users`）— 不出现 404  
- [ ] 上传媒体 — MinIO 正常（若失败查 S3 环境变量）  

---

## 十三、日常发布与运维

### 13.1 只改前端

```bash
cd /www/wwwroot/cenkor-admin
git pull
bash scripts/build-frontends.sh
# 宝塔无需重启，用户强刷即可
```

### 13.2 只改后端

**Docker 方案 A：**

```bash
docker compose -f docker-compose.baota-static.yml --env-file .env.prod up -d --build backend
docker compose -f docker-compose.baota-static.yml exec -T backend alembic upgrade head
```

**宝塔 Python 方案 B：**

```bash
git pull
bash scripts/migrate-and-seed-host.sh    # 有 migration 时
# 宝塔 Python 项目 → 重启
# 或：bash scripts/restart-backend-host.sh
```

### 13.3 备份

```bash
bash scripts/backup.sh
```

### 13.4 查看日志

| 方式 | 命令 / 位置 |
|------|-------------|
| Docker backend | `docker logs -f cenkor-backend` |
| 宝塔 Python | 面板 → Python 项目 → 日志 |
| 脚本启动 | `tail -f /tmp/cenkor-uvicorn.log` |
| Nginx | 宝塔 → 网站 → 日志 |

---

## 十四、常见问题

### Q1：首页显示 `{"detail":"Not Found"}`

**原因：** 整站反代到了 8002，而不是只反代 `/api/`。

**解决：** 删除 `location / { proxy_pass http://127.0.0.1:8002; }`，仅保留 `location /api/`；根目录必须指向 `dist`。

---

### Q2：宝塔报 `duplicate location "/"`

**原因：** 伪静态里写了 `location /`，与主配置冲突。

**解决：** 伪静态只用 [`rewrite-admin.conf`](../deploy/baota/rewrite-admin.conf) 的 `if + rewrite`，不要写 `location /`。

---

### Q3：Python 项目列表里没有 cenkor

**原因：** 用了 Docker backend 或 `nohup` 脚本启动，未在宝塔注册 Python 项目。

**解决：** 正常。若要出现在列表里，改用 [方案 B](#62-方案-b宝塔-python-项目推荐与-lightmes-一致) 添加项目。

---

### Q4：`password authentication failed` / Redis AUTH 失败

**原因：** 宝塔 Python 项目仍使用 `.env.prod` 里的 `postgres:5432` / `redis:6379`。

**解决：** 环境变量改为 `127.0.0.1:5433` / `127.0.0.1:6380`，密码与 Docker 容器一致。参考 [`env.host.override`](../deploy/examples/env.host.override)。

---

### Q5：`service "backend" is not running`（docker compose exec）

**原因：** 中间件在 Docker，backend 用宝塔 Python 跑，没有 `cenkor-backend` 容器。

**解决：** 迁移改用 `bash scripts/migrate-and-seed-host.sh`，不要用 `docker compose exec backend`。

---

### Q6：401 登录后立即退出

**原因：** 旧版前端未实现 refresh token；或 `SECRET_KEY` 变更导致 token 失效。

**解决：** 重新 `bash scripts/build-frontends.sh` 部署最新 dist；清除浏览器 localStorage 后重登。

---

### Q7：媒体上传失败 / S3 SignatureDoesNotMatch

**原因：** `S3_SECRET_KEY` 与 MinIO 容器 `MINIO_ROOT_PASSWORD` 不一致。

**解决：**

```bash
docker inspect cenkor-minio --format '{{range .Config.Env}}{{println .}}{{end}}' | grep MINIO_ROOT
```

将正确值写入环境变量并重启 backend。

---

### Q8：可选 — API 独立子域

添加站点 `api.cenkor.cn`，类型反向代理，配置见 [`deploy/baota/nginx-api.example.conf`](../deploy/baota/nginx-api.example.conf)。

构建前端时：

```bash
VITE_API_BASE_URL=https://api.cenkor.cn bash scripts/build-frontends.sh
```

---

### Q9：可选 — 官网 www.cenkor.cn

官网为**独立扩展**，不在核心打包内。CMS 对接见 [`docs/addons/WEBSITE_CMS.md`](addons/WEBSITE_CMS.md)。

要点：官网站点也需 `location /api/` 反代到 `127.0.0.1:8002`，供公开 CMS 数据读取。

---

## 附录：配置文件速查

| 文件 | 用途 |
|------|------|
| [`deploy/baota/rewrite-admin.conf`](../deploy/baota/rewrite-admin.conf) | admin 伪静态 |
| [`deploy/baota/rewrite-portal.conf`](../deploy/baota/rewrite-portal.conf) | portal 伪静态 |
| [`deploy/baota/server-snippet-admin-api.conf`](../deploy/baota/server-snippet-admin-api.conf) | admin API 反代 |
| [`deploy/baota/server-snippet-portal-api.conf`](../deploy/baota/server-snippet-portal-api.conf) | portal API 反代 |
| [`deploy/baota/nginx-api.example.conf`](../deploy/baota/nginx-api.example.conf) | 独立 API 子域 |
| [`deploy/examples/env.host.override`](../deploy/examples/env.host.override) | 宝塔 Python 环境变量模板 |
| [`docker-compose.baota-static.yml`](../docker-compose.baota-static.yml) | Docker 栈定义 |
| [`scripts/deploy-baota-static.sh`](../scripts/deploy-baota-static.sh) | 一键部署 |
| [`scripts/build-frontends.sh`](../scripts/build-frontends.sh) | 构建 dist |
| [`scripts/restart-backend-host.sh`](../scripts/restart-backend-host.sh) | 重启裸进程 backend |
| [`scripts/migrate-and-seed-host.sh`](../scripts/migrate-and-seed-host.sh) | 宿主机迁移 + seed |

---

**默认账号：** `admin@cenkor.cn` / `admin123`（上线后请修改）




我执行的命令（你可照抄）
① 先看谁在占 8002：
ss -tlnp | grep ':8002 '
ps aux | grep 'uvicorn.*8002' | grep -v grep
② 停掉（推荐顺序）：
# 若是之前脚本起的，有 pid 文件
kill $(cat /tmp/cenkor-uvicorn.pid 2>/dev/null) 2>/dev/null
￼
# 按端口杀（主进程 + worker）
for pid in $(ss -tlnp | grep ':8002 ' | grep -oP 'pid=\K[0-9]+' | sort -u); do  
kill "$pid"
done
③ 2 秒后还没停，再强杀：
for pid in $(ss -tlnp | grep ':8002 ' | grep -oP 'pid=\K[0-9]+' | sort -u); do  
kill -9 "$pid"
done
④ 确认已释放：
ss -tlnp | grep ':8002 ' || echo "8002 已释放"
curl http://127.0.0.1:8002/api/health   # 应连不上



宝塔「添加 Python 项目」填写表
字段	填什么
项目名称
cenkor-admin（建议别叫 backend，避免和 openai 的 backend 混淆）
Python 环境
可暂时选 lightmes（3.14），更推荐在「环境管理」新建 Python 3.12 专给 cenkor
启动方式
命令行启动 ✅（你已选对）
项目路径
/www/wwwroot/cenkor-admin/backend ✅（你已选对）
启动命令
见下方 ⬇️
环境变量
选 从文件加载
环境变量文件
/www/wwwroot/cenkor-admin/deploy/baota/cenkor-backend.host.env
启动用户
www（与 lightmes 一致）
安装依赖包
/www/wwwroot/cenkor-admin/backend（选含 pyproject.toml 的目录）
启动命令（复制粘贴）
python3 -m uvicorn cenkor_admin.main:app --host 127.0.0.1 --port 8002 --workers 2
若选了 lightmes 环境，宝塔有时要用该环境的 python 全路径，可改成：

/www/server/pyporject_evn/lightmes/bin/python3 -m uvicorn cenkor_admin.main:app --host 127.0.0.1 --port 8002 --workers 2
环境变量文件