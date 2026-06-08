#!/bin/bash
# 生成自签 SSL 证书（**仅测试用**，生产请用 Let's Encrypt）
set -e
cd "$(dirname "$0")/../deploy/nginx"
mkdir -p certs

DOMAIN=${1:-cenkor.cn}

openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout certs/privkey.pem \
  -out certs/fullchain.pem \
  -days 365 \
  -subj "/C=CN/ST=Beijing/L=Beijing/O=Cenkor/CN=$DOMAIN" \
  -addext "subjectAltName=DNS:$DOMAIN,DNS:*.$DOMAIN"

chmod 600 certs/privkey.pem
echo "✓ 自签证书生成完毕（365 天有效，仅供开发测试）"
echo "  certs/fullchain.pem"
echo "  certs/privkey.pem"
echo ""
echo "⚠️ 生产请用 certbot 申请真正的证书："
echo "  certbot certonly --webroot -w /var/www/cenkor-web -d cenkor.cn -d www.cenkor.cn -d admin.cenkor.cn -d api.cenkor.cn"
