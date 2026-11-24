#!/usr/bin/env bash
# Cenkor Admin · 全栈 Docker 一键部署
#
#   bash scripts/bootstrap-fullstack.sh                   # 自动选源（默认）
#   bash scripts/bootstrap-fullstack.sh --mirror cn       # 强制国内镜像（WSL / 大陆机器）
#   bash scripts/bootstrap-fullstack.sh --mirror global   # 强制官方源（海外服务器 / CI）
#
# 做的三件事：
#   1. 没有 .env 就生成一份（随机密钥 + 自动填本机 IP），并按网络情况写入软件源
#   2. 构建并启动全部容器：PostgreSQL + Redis + MinIO + 后端 + Celery + 三个前端
#   3. 等后端就绪，打印各访问地址与初始管理员口令
#
# 幂等：.env 已存在时沿用；重复执行只做重建与重启。
# 显式传 --mirror 时会同步改写 .env 的 APT_MIRROR / PIP_INDEX_URL / NPM_REGISTRY 三行。
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_TEMPLATE="docker/fullstack/env.fullstack.example"
COMPOSE_BASE="docker compose -f docker-compose.fullstack.yml"

say()  { printf '\033[36m▸\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
用法：bash scripts/bootstrap-fullstack.sh [--mirror auto|cn|global]

  --mirror auto     默认。探测 pypi.org 首字节耗时，偏慢则自动切国内镜像
  --mirror cn       强制国内镜像（阿里云 / 清华 / 腾讯云，自动选第一个可达的）
  --mirror global   强制官方源（海外服务器、GitHub Actions 等）
  -h, --help        显示本帮助

国内 / WSL2 构建慢到 30 kB/s 量级时，用 --mirror cn。
显式传 --mirror 时会同步改写已存在 .env 的软件源三行，不用手工编辑。
EOF
}

# ---------- 参数解析 ----------
# MIRROR_MODE: auto（默认，探测后决定）| cn（强制国内）| global（强制官方）
MIRROR_MODE="auto"
MIRROR_EXPLICIT=0

while [ $# -gt 0 ]; do
  case "$1" in
    --mirror)
      [ $# -ge 2 ] || die "--mirror 需要一个值：auto | cn | global"
      MIRROR_MODE="$2"; MIRROR_EXPLICIT=1; shift 2 ;;
    --mirror=*)
      MIRROR_MODE="${1#--mirror=}"; MIRROR_EXPLICIT=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      die "未知参数：$1（可用：--mirror auto|cn|global，详见 --help）" ;;
  esac
done

case "$MIRROR_MODE" in
  auto|cn|global) ;;
  *) die "--mirror 只接受 auto / cn / global，收到：$MIRROR_MODE" ;;
esac

# ---------- 前置检查 ----------
command -v docker >/dev/null 2>&1 || die "未找到 docker，请先安装 Docker"
docker compose version >/dev/null 2>&1 || die "缺少 docker compose 插件（v2+）"
# curl 既用于镜像探测，也用于后面的就绪等待，缺了会静默卡住，先检查
command -v curl >/dev/null 2>&1 || die "未找到 curl，请先安装（apt install curl）"

rand_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$1"
  else
    head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

detect_ip() {
  if hostname -I >/dev/null 2>&1; then
    hostname -I 2>/dev/null | awk '{print $1}'
  fi
}
IP="$(detect_ip || true)"

# 开发者门户（应用中心）是**闭源模块**，不在开源仓库中（见 .gitignore 的 frontend/developer-web/）。
# 这里自动探测：源码齐全就带上 developer profile 一起构建，公开 clone 则静默跳过。
if [ -d frontend/developer-web ]; then
  COMPOSE_BASE="$COMPOSE_BASE --profile developer"
  WITH_DEVELOPER=1
else
  WITH_DEVELOPER=0
fi

# ---------- 软件源决策 ----------
# 三条构建变量的默认值必须与 compose 文件的 `:-` 兜底一致，
# 否则「.env 里注释掉」和「docker 层默认」会出现两种行为。
MK_NAME="official"
MK_PIP="https://pypi.org/simple"
MK_APT="deb.debian.org"
MK_NPM="https://registry.npmjs.org"

# 国内候选源，按优先级排列；字段用 | 分隔：名称|pip|apt 域名|npm
MIRROR_CANDIDATES=(
  "阿里云|https://mirrors.aliyun.com/pypi/simple/|mirrors.aliyun.com|https://registry.npmmirror.com"
  "清华|https://pypi.tuna.tsinghua.edu.cn/simple|mirrors.tuna.tsinghua.edu.cn|https://registry.npmmirror.com"
  "腾讯云|https://mirrors.cloud.tencent.com/pypi/simple/|mirrors.cloud.tencent.com|https://mirrors.cloud.tencent.com/npm/"
)

# 返回毫秒整数；不可达返回空串。--max-time 4 保证部署前不会长时间卡住。
probe_ms() {
  local url="$1" t
  t="$(curl -fsS -o /dev/null --max-time 4 -w '%{time_total}' "$url" 2>/dev/null || true)"
  [ -n "$t" ] || return 0
  awk -v t="$t" 'BEGIN { printf "%d", t * 1000 }'
}

# 按优先级探测国内镜像，第一个可达的写进 MK_*；全不可达返回 1。
pick_cn_mirror() {
  local entry name pip apt npm
  for entry in "${MIRROR_CANDIDATES[@]}"; do
    IFS='|' read -r name pip apt npm <<< "$entry"
    if curl -fsS -o /dev/null --max-time 4 "$pip" 2>/dev/null; then
      MK_NAME="$name"; MK_PIP="$pip"; MK_APT="$apt"; MK_NPM="$npm"
      return 0
    fi
  done
  return 1
}

decide_mirror() {
  local t
  case "$MIRROR_MODE" in
    cn)
      if pick_cn_mirror; then
        say "软件源：已启用国内镜像（$MK_NAME）"
      else
        warn "阿里云 / 清华 / 腾讯云三个镜像都不可达，回退官方源（构建可能很慢）"
      fi
      ;;
    global)
      say "软件源：官方（deb.debian.org / pypi.org / registry.npmjs.org）"
      ;;
    auto)
      t="$(probe_ms 'https://pypi.org/simple/pip/')"
      if [ -z "$t" ]; then
        warn "探测 pypi.org 超时或不可达（>4s）"
      else
        say "pypi.org 首字节 ${t} ms"
      fi
      # 海外 / 优质网络首字节通常 < 800ms；国内直连常见 2000ms 以上。
      if [ -z "$t" ] || [ "$t" -gt 1500 ]; then
        if pick_cn_mirror; then
          say "网络偏慢，自动启用国内镜像（$MK_NAME）"
          warn "要换回官方源：bash scripts/bootstrap-fullstack.sh --mirror global"
        else
          warn "国内镜像也不可达，继续用官方源（构建会很慢）"
        fi
      else
        say "网络正常，使用官方源"
      fi
      ;;
  esac
}

# 把三行软件源写进已存在的 .env：mode=on 启用，mode=off 注释掉。
# 旧 .env 里没有这三行时追加一节，避免静默丢掉用户的镜像设置。
write_mirror_to_env() {
  local mode="$1" tmp=".env.tmp.$$"
  awk -v mode="$mode" -v pip="$MK_PIP" -v apt="$MK_APT" -v npm="$MK_NPM" '
    BEGIN { ha = 0; hp = 0; hn = 0 }
    /^#?APT_MIRROR=/    { if (mode == "on") print "APT_MIRROR=" apt;       else print "#APT_MIRROR=" apt;       ha = 1; next }
    /^#?PIP_INDEX_URL=/ { if (mode == "on") print "PIP_INDEX_URL=" pip;    else print "#PIP_INDEX_URL=" pip;    hp = 1; next }
    /^#?NPM_REGISTRY=/  { if (mode == "on") print "NPM_REGISTRY=" npm;     else print "#NPM_REGISTRY=" npm;     hn = 1; next }
    { print }
    END {
      if (!(ha && hp && hn)) {
        print ""
        print "# ---------- 构建加速（由 bootstrap --mirror 写入） ----------"
        if (mode == "on") {
          if (!ha) print "APT_MIRROR=" apt
          if (!hp) print "PIP_INDEX_URL=" pip
          if (!hn) print "NPM_REGISTRY=" npm
        } else {
          if (!ha) print "#APT_MIRROR=" apt
          if (!hp) print "#PIP_INDEX_URL=" pip
          if (!hn) print "#NPM_REGISTRY=" npm
        }
      }
    }
  ' .env > "$tmp"
  mv "$tmp" .env
  chmod 600 .env
}

# .env 里是否已有启用的镜像源（有值且未被注释）
env_mirror_on() {
  grep -qE '^PIP_INDEX_URL=.+' .env 2>/dev/null
}

decide_mirror
if [ "$MK_NAME" = "official" ]; then
  MIRROR_ENV_STATE="off"
else
  MIRROR_ENV_STATE="on"
fi

# ---------- 1. 生成 .env ----------
if [ -f .env ]; then
  say ".env 已存在，沿用现有配置（要重新生成请先删除 .env）"
  if [ "$MIRROR_EXPLICIT" = 1 ]; then
    write_mirror_to_env "$MIRROR_ENV_STATE"
    say "已按 --mirror $MIRROR_MODE 改写 .env 的软件源三行"
  elif [ "$MIRROR_ENV_STATE" = "on" ] && ! env_mirror_on; then
    # auto 探测到慢网络，但 .env 是之前生成的、没开镜像 —— 只提示不擅自改文件
    warn "当前网络偏慢，而 .env 未启用国内镜像。启用方式："
    warn "  bash scripts/bootstrap-fullstack.sh --mirror cn"
  fi
else
  [ -f "$ENV_TEMPLATE" ] || die "缺少模板 $ENV_TEMPLATE"
  say "生成 .env（随机密钥）"

  PG_PW="$(rand_hex 16)"
  MINIO_PW="$(rand_hex 16)"
  SECRET="$(rand_hex 48)"

  awk -v pg="$PG_PW" -v mo="$MINIO_PW" -v sk="$SECRET" -v ip="$IP" \
      -v mm="$MIRROR_ENV_STATE" -v mpip="$MK_PIP" -v mapt="$MK_APT" -v mnpm="$MK_NPM" '
    /^#POSTGRES_PASSWORD=/   { print "POSTGRES_PASSWORD=" pg; next }
    /^#MINIO_ROOT_PASSWORD=/ { print "MINIO_ROOT_PASSWORD=" mo; next }
    /^S3_SECRET_KEY=/        { print "S3_SECRET_KEY=" mo; next }
    /^#SECRET_KEY=/          { print "SECRET_KEY=" sk; next }
    /^PUBLIC_BASE_URL=/      { if (ip != "") print "PUBLIC_BASE_URL=http://" ip ":5185"; else print; next }
    /^CORS_ORIGINS=/         { if (ip != "") print "CORS_ORIGINS=http://" ip ":5185,http://" ip ":5192,http://" ip ":5175"; else print; next }
    /^#?APT_MIRROR=/         { if (mm == "on") print "APT_MIRROR=" mapt; else print "#APT_MIRROR=" mapt; next }
    /^#?PIP_INDEX_URL=/      { if (mm == "on") print "PIP_INDEX_URL=" mpip; else print "#PIP_INDEX_URL=" mpip; next }
    /^#?NPM_REGISTRY=/       { if (mm == "on") print "NPM_REGISTRY=" mnpm; else print "#NPM_REGISTRY=" mnpm; next }
    { print }
  ' "$ENV_TEMPLATE" > .env

  [ -n "$(tail -c 1 .env)" ] && printf '\n' >> .env
  chmod 600 .env
  say "已写入 .env（权限 600，含随机 POSTGRES_PASSWORD / MINIO_ROOT_PASSWORD / SECRET_KEY）"
  if [ "$MIRROR_ENV_STATE" = "on" ]; then
    say "已在 .env 中启用国内镜像（$MK_NAME）"
  fi
fi

env_get() {
  grep -E "^${1}=" .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r' || true
}

# ---------- 2. 构建并启动 ----------
say "构建镜像并启动容器（首次构建需数分钟，请耐心等待）"
$COMPOSE_BASE up -d --build

# ---------- 3. 等后端就绪 ----------
BACKEND_PORT="$(env_get FS_BACKEND_PORT)"; BACKEND_PORT="${BACKEND_PORT:-8001}"
ADMIN_PORT="$(env_get FS_ADMIN_WEB_PORT)"; ADMIN_PORT="${ADMIN_PORT:-5185}"
PORTAL_PORT="$(env_get FS_PORTAL_WEB_PORT)"; PORTAL_PORT="${PORTAL_PORT:-5192}"
DEV_PORT="$(env_get FS_DEVELOPER_WEB_PORT)"; DEV_PORT="${DEV_PORT:-5175}"

say "等待后端就绪：127.0.0.1:${BACKEND_PORT}/api/health"
ready=0
for _ in $(seq 1 60); do
  if curl -fsS -o /dev/null "http://127.0.0.1:${BACKEND_PORT}/api/health" 2>/dev/null; then
    ready=1
    break
  fi
  sleep 3
done
if [ "$ready" = 1 ]; then
  say "后端已就绪"
else
  warn "等待超时（后端可能仍在迁移/建表），请查看：$COMPOSE_BASE logs backend"
fi

# ---------- 4. 汇总输出 ----------
HOST="${IP:-localhost}"
echo
echo "======================== 部署完成 ========================"
echo "  管理后台    http://${HOST}:${ADMIN_PORT}"
echo "  用户中心    http://${HOST}:${PORTAL_PORT}"
if [ "${WITH_DEVELOPER:-0}" = 1 ]; then
  echo "  开发者门户  http://${HOST}:${DEV_PORT}"
fi
echo "  API 文档    http://${HOST}:${BACKEND_PORT}/api/docs"
echo "  健康检查    http://${HOST}:${BACKEND_PORT}/api/health"
echo "=========================================================="
if [ "${WITH_DEVELOPER:-0}" != 1 ]; then
  echo
  echo "  提示：未包含 frontend/developer-web（闭源的应用中心），已跳过开发者门户。"
  echo "        在源码齐全的机器上可加 --profile developer 启用。"
fi
echo
# ⚠️ 必须先把日志取到变量、再用 bash 内建匹配来判断。
#    本脚本开了 set -euo pipefail，而 `logs ... | grep -q` 里 grep 一命中就退出，
#    上游 docker compose 会收到 SIGPIPE 并以非 0 退出 -> pipefail 判定整条管道失败
#    -> if 永远走 else，初始口令再也打不出来（且误报「已存在」）。
BACKEND_LOG="$($COMPOSE_BASE logs backend 2>/dev/null || true)"
if [[ "$BACKEND_LOG" == *"已创建管理员"* ]]; then
  printf '%s\n' "$BACKEND_LOG" | grep -B 1 -A 2 "已创建管理员" | tail -8 || true
  echo "  （口令只显示这一次，请立即登录并修改）"
else
  echo "  本次日志中没有新建管理员的口令（该库的管理员此前已存在）。"
  echo "  口令只在首次初始化时打印一次；容器重建后日志会消失，此时只能重置："
  echo "      bash scripts/reset-admin-password.sh"
fi
echo
echo "常用运维："
echo "  $COMPOSE_BASE ps            # 查看容器状态"
echo "  $COMPOSE_BASE logs -f backend"
echo "  $COMPOSE_BASE down          # 停止（保留数据卷）"
echo
