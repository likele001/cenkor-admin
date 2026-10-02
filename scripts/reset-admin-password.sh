#!/bin/bash
# 重置管理员口令 —— Docker 全栈 / 宿主机 uvicorn 两种部署都适用
#
# 为什么需要它：管理员口令库里只存 bcrypt hash（不可逆），明文只在 seed 首次创建时
# 打印一次。一旦容器被重建（`docker compose down` 再 `up`），日志里那行就没了，
# 而 seed 因为「管理员已存在」会直接跳过 —— 此时只能重置。
#
# 用法：
#   bash scripts/reset-admin-password.sh                        # 随机生成并打印
#   bash scripts/reset-admin-password.sh --password 'NewPass1'  # 指定新口令
#   bash scripts/reset-admin-password.sh --email other@cenkor.cn
#
# 环境变量：
#   COMPOSE_FILE=xxx.yml      指定 compose 文件（默认 docker-compose.fullstack.yml）
#   BACKEND_PYTHON=/path/py   宿主机模式下的解释器（默认宝塔 venv，回退 PATH 上的 python3）
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
BACKEND_DIR="$ROOT/backend"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.fullstack.yml}"
MODULE="cenkor_admin.scripts.reset_admin_password"
MODULE_FILE="$BACKEND_DIR/src/cenkor_admin/scripts/reset_admin_password.py"

# ---- 1) Docker 全栈部署：容器在跑就在容器内执行（环境变量已由 compose 注入）----
# ⚠️ 不用 `... | head -1`：本脚本开了 pipefail，head 提前退出会让上游吃 SIGPIPE
#    并以非 0 退出，整条管道被判失败（本仓库已经踩过这个坑）。改用参数展开取首行。
CID="$(docker compose -f "$COMPOSE_FILE" ps -q backend 2>/dev/null || true)"
CID="${CID%%$'\n'*}"
if [ -n "$CID" ] && [ "$(docker inspect -f '{{.State.Running}}' "$CID" 2>/dev/null || true)" = "true" ]; then
  echo "▸ 检测到 Docker 全栈部署（$COMPOSE_FILE），在 backend 容器内执行"
  # 镜像是构建时的快照：若宿主机代码比镜像新（比如 git pull 了但没重建），
  # 容器里找不到这个模块 → 退化为把宿主机脚本经 stdin 送进容器执行
  # （容器内本来就装了 cenkor_admin 包，脚本用的是绝对导入，所以照样能跑）。
  if docker compose -f "$COMPOSE_FILE" exec -T backend \
       python -c "import cenkor_admin.scripts.reset_admin_password" >/dev/null 2>&1; then
    exec docker compose -f "$COMPOSE_FILE" exec -T backend python -m "$MODULE" "$@"
  fi
  echo "  （容器内没有该模块：镜像是旧版本，改用宿主机脚本经 stdin 执行）"
  exec docker compose -f "$COMPOSE_FILE" exec -T backend python - "$@" < "$MODULE_FILE"
fi

# ---- 2) 宿主机裸进程（宝塔 / uvicorn）----
# config.py 的 _find_env_file() 会自动找到 backend/.env，无需手工拼 DATABASE_URL。
echo "▸ 未发现运行中的 backend 容器，按宿主机模式执行"
PYTHON_BIN="${BACKEND_PYTHON:-/www/server/pyporject_evn/cenkor/bin/python3}"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="$(command -v python3)"

cd "$BACKEND_DIR"
export PYTHONPATH=src
exec "$PYTHON_BIN" -m "$MODULE" "$@"
