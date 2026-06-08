#!/bin/bash
# 生成生产强密码
set -e
cd "$(dirname "$0")/.."

PG_PW=$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)
MINIO_PW=$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)
REDIS_PW=$(openssl rand -base64 18 | tr -d '/+=' | head -c 24)
JWT_SECRET=$(openssl rand -hex 32)

if [ -f .env.prod ]; then
  echo "⚠ .env.prod 已存在。覆盖？(y/N)"
  read -p "> " overwrite
  [ "$overwrite" = "y" ] || [ "$overwrite" = "Y" ] || exit 0
fi

cat > .env.prod <<EOF
# =============================================================
# Cenkor Admin · 生产环境变量
# 生成时间: $(date -Iseconds)
# ⚠️ git 忽略（见 .gitignore）
# =============================================================

APP_NAME=Cenkor Admin
APP_VERSION=0.1.0
APP_ENV=production
DEBUG=false
COMPOSE_PROJECT_NAME=cenkor-admin-prod

# ---- 安全 ----
SECRET_KEY=$JWT_SECRET
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# ---- PostgreSQL 16 ----
POSTGRES_DB=cenkor
POSTGRES_USER=cenkor
POSTGRES_PASSWORD=$PG_PW
POSTGRES_PORT=5432

# ---- Redis 7 ----
REDIS_PASSWORD=$REDIS_PW
REDIS_PORT=6379

# ---- MinIO ----
MINIO_ROOT_USER=minio
MINIO_ROOT_PASSWORD=$MINIO_PW
MINIO_API_PORT=9000
MINIO_CONSOLE_PORT=9001

# ---- Backend (FastAPI) ----
BACKEND_PORT=8000
DATABASE_URL=postgresql+asyncpg://cenkor:$PG_PW@postgres:5432/cenkor
DATABASE_URL_SYNC=postgresql://cenkor:$PG_PW@postgres:5432/cenkor
REDIS_URL=redis://:$REDIS_PW@redis:6379/0
# 宿主机裸跑 backend（PG/Redis 映射到 127.0.0.1）时改用：
# DATABASE_URL=postgresql+asyncpg://cenkor:$PG_PW@127.0.0.1:5433/cenkor
# DATABASE_URL_SYNC=postgresql://cenkor:$PG_PW@127.0.0.1:5433/cenkor
# REDIS_URL=redis://:$REDIS_PW@127.0.0.1:6380/0
S3_ENDPOINT=http://minio:9000
S3_API_PORT=9000
S3_ACCESS_KEY=minio
S3_SECRET_KEY=$MINIO_PW
S3_BUCKET_PUBLIC=cenkor-public
S3_BUCKET_PRIVATE=cenkor-private
S3_REGION=us-east-1

# 飞书 OAuth（**填你的** APP_ID 和 APP_SECRET）
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_REDIRECT_URI=https://admin.example.com/auth/feishu/callback

# 逗号分隔；部署时改为你的 admin / portal 域名
CORS_ORIGINS=https://admin.example.com,https://portal.example.com
PUBLIC_BASE_URL=

ADMIN_WEB_PORT=5173
ADMIN_WEB_HOST_PORT=5174
PORTAL_WEB_HOST_PORT=5175
BACKEND_HOST_PORT=8002
VITE_API_BASE_URL=
VITE_WS_URL=
EOF

chmod 600 .env.prod
echo "✓ .env.prod 已生成（强密码 + JWT secret）"
echo ""
echo "生成的强密码："
echo "  PG:        $PG_PW"
echo "  Redis:     $REDIS_PW"
echo "  MinIO:     $MINIO_PW"
echo "  JWT:       $JWT_SECRET"
echo ""
echo "⚠️ 备份到 1Password / Vault！丢失 = 重置所有密码"
echo ""
echo "Cenkor 生产域名片段（可选）：deploy/examples/env.cenkor.snippet"
