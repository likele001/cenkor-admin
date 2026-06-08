#!/bin/bash
# =============================================================
# Cenkor Admin · 域名 + SSL 一键配置脚本
# =============================================================
set -e

# ===== 在这里改你的配置 =====
ROOT_DOMAIN="cenkor.cn"
SERVER_IP="104.152.50.138"
ADMIN_EMAIL="admin@${ROOT_DOMAIN}"
NGINX_MODE="baota"  # baota | docker | baota-static

# ============================
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info() { echo -e "${GREEN}▸${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; exit 1; }

cd "$(dirname "$0")/.."

# === 1. 检查 ===
info "检查环境..."
[ -f ".env.prod" ] || err ".env.prod 不存在，先跑：bash scripts/gen-secrets.sh"
command -v docker >/dev/null 2>&1 || err "请先安装 Docker"
info "  ✓ .env.prod 存在"

# === 2. DNS 检查 ===
info "检查 DNS 解析（4 个子域名都应解析到 ${SERVER_IP}）..."
for sub in "" "www" "api" "admin"; do
  host="${sub}.${ROOT_DOMAIN}"
  if [ -z "$sub" ]; then host="$ROOT_DOMAIN"; fi
  # 用 python 查 DNS（不依赖 dig）
  ip=$(python3 -c "
import socket
try:
  print(socket.gethostbyname('$host'))
except:
  print('NXDOMAIN')
")
  if [ "$ip" = "$SERVER_IP" ]; then
    info "  ✓ $host → $ip"
  else
    warn "  $host → $ip（应为 $SERVER_IP）"
  fi
done

# === 3. 80/443 检查 ===
info "检查 80/443 端口..."
if ss -tln 2>/dev/null | grep -qE ":80\b|:443\b"; then
  pid=$(ss -tlnp 2>/dev/null | grep ":80\b" | grep -oP 'pid=\K[0-9]+' | head -1)
  if [ -n "$pid" ]; then
    proc=$(ps -p "$pid" -o comm= 2>/dev/null)
    warn "  80/443 已被 $proc (PID $pid) 占用"
  fi
  if [ "$NGINX_MODE" = "docker" ]; then
    warn "  Docker 模式需要先停宝塔 nginx："
    echo "    systemctl stop nginx"
    echo "    systemctl disable nginx  # 开机不启动"
    read -p "  继续？(y/N) " ok
    [ "$ok" = "y" ] || [ "$ok" = "Y" ] || err "已取消"
  else
    if [ "$NGINX_MODE" = "baota-static" ]; then
      info "  宝塔静态 dist 模式：站点根目录指 frontend/*/dist，详见 docs/BAOTA_STATIC_DEPLOY.md"
    else
      info "  宝塔模式：现有 nginx 作为反代层"
    fi
  fi
else
  info "  ✓ 80/443 空闲"
fi

# === 4. 证书准备 ===
CERT_DIR="deploy/nginx/certs"
mkdir -p "$CERT_DIR"
info "检查证书..."

if [ -f "$CERT_DIR/fullchain.pem" ] && [ -f "$CERT_DIR/privkey.pem" ]; then
  # 检查有效期
  exp=$(openssl x509 -enddate -noout -in "$CERT_DIR/fullchain.pem" 2>/dev/null | cut -d= -f2)
  info "  ✓ 已有证书（$exp 到期）"
else
  if [ "$NGINX_MODE" = "baota" ]; then
    warn "  证书在宝塔：/www/server/panel/vhost/cert/${ROOT_DOMAIN}/"
    warn "  复制："
    echo "    cp /www/server/panel/vhost/cert/${ROOT_DOMAIN}/fullchain.pem ${CERT_DIR}/"
    echo "    cp /www/server/panel/vhost/cert/${ROOT_DOMAIN}/privkey.pem ${CERT_DIR}/"
    read -p "  已复制了？(y/N) " ok
    [ "$ok" = "y" ] || [ "$ok" = "Y" ] || err "已取消"
  else
    warn "  证书缺失，尝试 certbot 自动申请..."
    if ! command -v certbot >/dev/null 2>&1; then
      warn "  certbot 未装，尝试 snap（Ubuntu）..."
      if command -v snap >/dev/null 2>&1; then
        snap install --classic certbot
        ln -sf /snap/bin/certbot /usr/local/bin/certbot 2>/dev/null || true
      else
        err "  请先装 certbot：apt install certbot 或 snap install certbot --classic"
      fi
    fi
    certbot certonly --webroot -w /var/www/html \
      -d "$ROOT_DOMAIN" -d "www.$ROOT_DOMAIN" -d "api.$ROOT_DOMAIN" -d "admin.$ROOT_DOMAIN" \
      --email "$ADMIN_EMAIL" --agree-tos --non-interactive
    cp /etc/letsencrypt/live/"$ROOT_DOMAIN"/fullchain.pem "$CERT_DIR/"
    cp /etc/letsencrypt/live/"$ROOT_DOMAIN"/privkey.pem "$CERT_DIR/"
    info "  ✓ 证书已申请并复制"
  fi
fi

# === 5. 更新 .env.prod 域名 ===
info "更新 .env.prod 域名配置..."
sed -i.bak "s|cenkor.cn|${ROOT_DOMAIN}|g; s|CORS_ORIGINS=.*|CORS_ORIGINS=https://${ROOT_DOMAIN},https://www.${ROOT_DOMAIN},https://admin.${ROOT_DOMAIN}|; s|PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://api.${ROOT_DOMAIN}|; s|FEISHU_REDIRECT_URI=.*|FEISHU_REDIRECT_URI=https://admin.${ROOT_DOMAIN}/auth/feishu/callback|" .env.prod
info "  ✓ .env.prod 已更新"

# === 6. 提示下一步 ===
echo ""
info "✅ 域名配置准备就绪"
echo ""
echo "═══════════════════════════════════════════"
echo "  下一步（任选其一）："
echo "═══════════════════════════════════════════"
echo ""
echo "  【A】宝塔模式（推荐，5 分钟）："
echo "    1. 浏览器开宝塔面板 → 网站 → 添加站点"
echo "    2. 域名: ${ROOT_DOMAIN} www.${ROOT_DOMAIN} api.${ROOT_DOMAIN} admin.${ROOT_DOMAIN}"
echo "    3. SSL → Let's Encrypt → 申请 → 强制 HTTPS"
echo "    4. 反向代理 → 目标 URL: http://127.0.0.1:8002"
echo "    5. 起后端："
echo "       cd /www/wwwroot/cenkor-admin"
echo "       bash scripts/deploy.sh"
echo ""
echo "  【B】Docker nginx 模式（统一管理）："
echo "    1. 停宝塔 nginx：systemctl stop nginx"
echo "    2. 起 Docker：cd /www/wwwroot/cenkor-admin && bash scripts/deploy.sh"
echo "    3. 访问 https://${ROOT_DOMAIN}"
echo ""
echo "═══════════════════════════════════════════"
echo ""
warn "⚠ 首次登录后立刻改 admin 默认密码！"
warn "⚠ 检查防火墙：80/443/9002/9001 是否放行"
