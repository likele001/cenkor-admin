# Cenkor Admin · 域名绑定 + SSL 部署完整指南

> 适用：服务器 IP = `104.152.50.138`，域名 = `cenkor.cn`
> 已用宝塔面板（80/443 已被宝塔 nginx 占用）

## 📋 总览

你手上有的：
- ✅ 服务器公网 IP：`104.152.50.138`
- ✅ 宝塔面板（80/443 跑着，多个 vhost 已配）
- ✅ Docker（PG/Redis/MinIO/Backend/Admin-Web 都能起）
- ✅ 后端在 8002，前端 dev server 在 5174

你需要做的：
1. 域名 DNS 解析 → 104.152.50.138
2. 宝塔加 vhost + 申请 SSL
3. 宝塔反向代理到 Docker
4. 启动 Docker compose 生产栈
5. 验证 + 改强密码

---

## Step 1：域名 DNS 解析（5 分钟）

去你的域名注册商控制台（阿里云/腾讯云/Cloudflare 等），加 **4 条 A 记录**：

| 主机记录 | 记录类型 | 记录值 |
|---------|---------|--------|
| `@`     | A       | `104.152.50.138` |
| `www`   | A       | `104.152.50.138` |
| `api`   | A       | `104.152.50.138` |
| `admin` | A       | `104.152.50.138` |

生效时间：5-30 分钟（Cloudflare 30s，国内一般 5min）。

**验证**（服务器上执行）：
```bash
curl -s ifconfig.me  # 确认是 104.152.50.138
# 等 5 分钟后试：
for d in cenkor.cn www.cenkor.cn api.cenkor.cn admin.cenkor.cn; do
  echo -n "$d → "
  curl -sI --max-time 5 "http://$d" 2>&1 | head -1
done
# 期望：4 行都返 200/301/302
```

---

## Step 2：宝塔加 vhost + SSL（10 分钟）

### 2.1 登录宝塔
浏览器开 `http://104.152.50.138:8888/btpanel`（或你宝塔的实际端口）

### 2.2 加网站
- **网站** → **添加站点**
- 域名：`cenkor.cn www.cenkor.cn api.cenkor.cn admin.cenkor.cn`（一行一个或空格分隔）
- 备注：Cenkor Admin
- 根目录：`/www/wwwroot/cenkor-admin-website-bridge`（**新建空目录**，不创建 FTP/数据库）
- PHP 版本：**纯静态**

### 2.3 申请 SSL
- 站点设置 → **SSL** → **Let's Encrypt** → 选全部域名 → **申请**
- 申请成功后开启 **强制 HTTPS**

### 2.4 反向代理
- 站点设置 → **反向代理** → **添加反向代理**
- 代理名称：`cenkor-backend`
- 目标 URL：`http://127.0.0.1:8002`
- 发送域名：`$host`
- 内容替换：（留空）

### 2.5 admin 子域名独立反代（如果想后台单独走）
- 同样加一个站点，域名 = `admin.cenkor.cn`
- 反向代理到 `http://127.0.0.1:5174`

---

## Step 3：改 nginx 配置（直用 prod 模板）

宝塔的反代会跟我们的 `nginx.prod.conf` 冲突，**推荐用宝塔的反代 + 我们的应用容器**这条路（更简单）。

如果要直用 Docker 内 nginx（推荐生产 + 想统一管理）：
```bash
# 1. 停宝塔 nginx
systemctl stop nginx

# 2. 起 Docker
cd /www/wwwroot/cenkor-admin
bash scripts/deploy.sh

# 3. (可选) 关掉宝塔开机自启
systemctl disable nginx
```

---

## Step 4：启动生产 Docker 栈（5 分钟）

```bash
cd /www/wwwroot/cenkor-admin

# 1. .env.prod 已生成（含强密码）
cat .env.prod | head -5

# 2. 填飞书 OAuth（如已有 APP_ID/SECRET；没有也能跑）
nano .env.prod
# 找到 FEISHU_APP_ID / FEISHU_APP_SECRET 填上

# 3. 准备证书（如果走宝塔，证书已经在宝塔了；走 Docker 自管 nginx 用下面的）
mkdir -p deploy/nginx/certs
# 从宝塔拷证书：
cp /www/server/panel/vhost/cert/cenkor.cn/fullchain.pem deploy/nginx/certs/
cp /www/server/panel/vhost/cert/cenkor.cn/privkey.pem deploy/nginx/certs/

# 4. 启动
bash scripts/deploy.sh
```

脚本会自动：
- 构建 Docker 镜像
- 跑 migration
- 跑 seed
- 等后端健康

---

## Step 5：把后端/前端端口改到生产端口

**宝塔路径**（推荐）：上面 Step 2 已配 `http://127.0.0.1:8002` 反代，跳过本步。

**Docker nginx 路径**（直管 nginx）：
- `nginx.prod.conf` 已经在 80/443 反代 backend:8000 和 admin-web:5173
- 容器内 admin-web 跑 Vite preview（不是 dev）
- 改 `frontend/admin-web/Dockerfile`：用 `npm run build && npm run preview` 跑 4173 端口，nginx 反代改 4173

---

## Step 6：首登 + 改强密码（2 分钟）

1. 浏览器开 `https://admin.cenkor.cn`
2. 登录：`admin@cenkor.cn` / `admin123`（**首次后立刻改**）
3. 进 `/system/users` → 改 admin 密码为强密码
4. 进 `/cms/products` → 确认数据已加载
5. 进 `/cms/media` → 上传一张图测 MinIO

---

## Step 7：健康检查清单

```bash
# 1. HTTPS 是否生效
curl -I https://cenkor.cn
curl -I https://admin.cenkor.cn
curl -I https://api.cenkor.cn/api/health

# 2. 后端 API
curl -s https://api.cenkor.cn/api/v1/public/site | head

# 3. 媒体库（公网）
curl -I https://cenkor.cn:9002/cenkor-public/

# 4. MinIO 控制台
curl -I https://cenkor.cn:9001
```

---

## 🔄 完整流程图

```
用户浏览器
   │
   ├─→ https://cenkor.cn       (公网静态)
   ├─→ https://admin.cenkor.cn  (后台)
   └─→ https://api.cenkor.cn    (API)
        │
        ▼
   ┌─── 宝塔 nginx (443) ───┐
   │   ├─ /api/* → 127.0.0.1:8002 → Docker backend:8000
   │   ├─ /*  → 静态文件
   │   └─ admin.cenkor.cn → 127.0.0.1:5174
   └────────────────────┘
              │
              ▼
   ┌─── Docker Compose ───┐
   │   postgres:5432
   │   redis:6379
   │   minio:9000
   │   backend:8000
   │   admin-web:5173 (dev) / 4173 (prod preview)
   └────────────────────┘
```

---

## ⚠️ 常见坑

1. **80/443 被占用**：宝塔 nginx 在跑。我们的 `nginx.prod.conf` 用了 `listen 80/443`，**必须先停宝塔**（`systemctl stop nginx`）或者用**宝塔反代**绕过
2. **MinIO 9001 控制台需要单独开放**：宝塔里再加一个站点 `minio.cenkor.cn` 反代到 9001
3. **公网拉取 MinIO 媒体**：网站要能取 `https://cenkor.cn:9002/cenkor-public/...`，要么把 MinIO 9002 端口也反代，要么用后端做中转
4. **SSL 续期**：Let's Encrypt 90 天，宝塔自动续；如果用 Docker nginx，自己加 cron 跑 certbot renew

---

## 🚀 自动化脚本

我准备了 `scripts/setup-domain.sh` 一键配置。**先改 ROOT_DOMAIN 变量再跑**：
```bash
cd /www/wwwroot/cenkor-admin
nano scripts/setup-domain.sh  # 改 ROOT_DOMAIN
bash scripts/setup-domain.sh
```

脚本会：
- DNS 检查
- 生成 certbot 证书（如果用 Docker nginx 路径）
- 检查 80/443 占用
- 给出下一步提示
