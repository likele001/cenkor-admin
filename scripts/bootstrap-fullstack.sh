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

  --mirror auto     默认。实测各源下载吞吐，国内明显更快时才切镜像
  --mirror cn       强制国内镜像（阿里云 / 清华 / 腾讯云，比较吞吐后选最快的）
  --mirror global   强制官方源（海外服务器、GitHub Actions 等）
  -h, --help        显示本帮助

判断依据是实测下载吞吐，不是「能不能连上」——索引页 49ms 返回、
真实 wheel 只有 200 KB/s 的源确实存在，只看首字节会选中最慢的那个。
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

# 国内候选源，字段用 | 分隔：名称|pip 索引|apt 域名|npm registry。
# 注意：这个数组不是优先级顺序，真正选谁由下面的吞吐测速决定。
MIRROR_CANDIDATES=(
  "阿里云|https://mirrors.aliyun.com/pypi/simple/|mirrors.aliyun.com|https://registry.npmmirror.com"
  "清华|https://pypi.tuna.tsinghua.edu.cn/simple|mirrors.tuna.tsinghua.edu.cn|https://registry.npmmirror.com"
  "腾讯云|https://mirrors.cloud.tencent.com/pypi/simple/|mirrors.cloud.tencent.com|https://mirrors.cloud.tencent.com/npm/"
)

# ---------- 测速参数 ----------
# 探测对象不是索引页根路径，而是某个包的大体积索引页：aiohttp 版本极多，
# 这页有数百 KB，足以反映 CDN 吞吐。
#
# 为什么不再用 %{time_total} 测首字节：首字节只证明「服务器肯不肯应答」。
# 实测出现过索引页 49ms 返回、真实 wheel 下载却只有 200 KB/s 的情况
# —— 按顺序取第一个可达的，就会选中最慢的那个源，pip 照样跑 22 分钟。
# 必须用 %{speed_download} 测吞吐，才接近用户的真实下载体验。
PROBE_PATH="aiohttp/"
PROBE_TIMEOUT=6
# 低于此吞吐仅用于告警，不用来淘汰候选：官方源可能更慢，
# 淘汰只会让用户更惨。300 KB/s 是按 pip 串行下载 40 个依赖、
# 总下载量数百 MB 反推的，低于这个值必然是分钟级累加。
MIRROR_MIN_BPS=300000

# 字节/秒 -> 人类可读
fmt_bps() {
  awk -v b="$1" 'BEGIN {
    if (b >= 1048576)      printf "%.1f MB/s", b / 1048576;
    else if (b >= 1024)    printf "%.0f KB/s", b / 1024;
    else                   printf "%d B/s", b;
  }'
}

# 测吞吐：输出 "<bytes_per_sec> <sample_bytes>"；不可达或失败输出空串。
probe_bps() {
  local url="$1" out
  out="$(curl -fsS -o /dev/null --max-time "$PROBE_TIMEOUT" \
        -w '%{speed_download} %{size_download}' \
        "${url%/}/${PROBE_PATH}" 2>/dev/null || true)"
  [ -n "$out" ] || return 0
  local bps bytes
  bps="$(awk -v v="${out% *}"   'BEGIN { printf "%d", v }')"
  bytes="$(awk -v v="${out#* }" 'BEGIN { printf "%d", v }')"
  [ "${bps:-0}" -gt 0 ] || return 0
  printf '%s %s' "$bps" "$bytes"
}

# 三个国内候选全部测速，取吞吐最大的写进 MK_*。
# 全部不可达返回 1；有可达但都偏慢时仍选最快的那个（比官方源近）。
pick_cn_mirror() {
  local entry name pip apt npm res bps bytes
  local best_name="" best_pip="" best_apt="" best_npm="" best_bps=0
  local reachable=0
  for entry in "${MIRROR_CANDIDATES[@]}"; do
    IFS='|' read -r name pip apt npm <<< "$entry"
    res="$(probe_bps "$pip")"
    if [ -z "$res" ]; then
      printf '    - %s：不可达\n' "$name"
      continue
    fi
    reachable=1
    bps="${res% *}"; bytes="${res#* }"
    printf '    - %s：%s（样本 %s 字节）\n' "$name" "$(fmt_bps "$bps")" "$bytes"
    if [ "$bps" -gt "$best_bps" ]; then
      best_bps="$bps"; best_name="$name"
      best_pip="$pip"; best_apt="$apt"; best_npm="$npm"
    fi
  done
  [ "$reachable" -eq 1 ] || return 1
  MK_NAME="$best_name"; MK_PIP="$best_pip"; MK_APT="$best_apt"; MK_NPM="$best_npm"
  MK_BPS="$best_bps"
  return 0
}

# 测官方源吞吐，结果写进 OFFICIAL_BPS（不可达时留空）
probe_official() {
  local res
  OFFICIAL_BPS=""
  res="$(probe_bps "https://pypi.org/simple/")"
  [ -n "$res" ] || { printf '    - %s：不可达\n' "官方"; return 0; }
  OFFICIAL_BPS="${res% *}"
  printf '    - %s：%s（样本 %s 字节）\n' "官方" "$(fmt_bps "$OFFICIAL_BPS")" "${res#* }"
}

MK_BPS=0
OFFICIAL_BPS=""

decide_mirror() {
  # 已有可用的 .env 镜像配置、且用户没显式指定时，不重复测速（省 10~20 秒）。
  # 想重新测速就显式传 --mirror auto。
  if [ "$MIRROR_EXPLICIT" = 0 ] && [ -f .env ] \
     && grep -qE '^PIP_INDEX_URL=.+' .env 2>/dev/null; then
    MK_NAME="(取自 .env)"
    say "软件源：沿用 .env 中已启用的 PIP_INDEX_URL"
    return
  fi

  case "$MIRROR_MODE" in
    cn)
      say "正在测速国内镜像（每源最多 ${PROBE_TIMEOUT} 秒）"
      if pick_cn_mirror; then
        say "软件源：国内镜像 $MK_NAME（实测 $(fmt_bps "$MK_BPS")）"
        if [ "$MK_BPS" -lt "$MIRROR_MIN_BPS" ]; then
          warn "最快的国内镜像也只有 $(fmt_bps "$MK_BPS")，构建仍会偏慢"
          warn "若本机有可用代理，给 Docker 配上后改用 --mirror global 可能更快"
        fi
      else
        warn "阿里云 / 清华 / 腾讯云三个镜像都不可达，回退官方源（构建可能很慢）"
      fi
      ;;
    global)
      say "软件源：官方（deb.debian.org / pypi.org / registry.npmjs.org）"
      ;;
    auto)
      say "正在测速（官方源 + 三个国内镜像，最多约 $((PROBE_TIMEOUT * 4)) 秒）"
      probe_official
      if pick_cn_mirror; then
        # 国内源要比官方快 20% 以上才切，避免两边接近时来回摇摆
        if [ -z "$OFFICIAL_BPS" ] || [ "$MK_BPS" -gt $((OFFICIAL_BPS * 12 / 10)) ]; then
          say "软件源：国内镜像 $MK_NAME（实测 $(fmt_bps "$MK_BPS")）"
          if [ -n "$OFFICIAL_BPS" ]; then
            say "          官方源 $(fmt_bps "$OFFICIAL_BPS")，明显更慢"
          else
            say "          官方源不可达"
          fi
        else
          say "软件源：官方（实测 $(fmt_bps "$OFFICIAL_BPS")），国内镜像没有明显更快"
        fi
      else
        if [ -n "$OFFICIAL_BPS" ]; then
          say "软件源：官方（实测 $(fmt_bps "$OFFICIAL_BPS")），国内镜像全部不可达"
        else
          warn "官方源与国内镜像都不可达，仍用官方源（构建可能失败或极慢）"
        fi
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
