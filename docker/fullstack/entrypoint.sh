#!/bin/sh
# Cenkor Admin · 后端容器入口
#
#   1. 应用数据库迁移（alembic upgrade head）
#   2. 首次启动自动灌入种子数据（幂等，已存在即跳过）→ 管理员初始口令打印在容器日志里
#
# 关闭方式：
#   SKIP_MIGRATE=1     跳过迁移
#   SEED_ON_STARTUP=0  跳过种子数据
#
# 说明：原来这两步要用户手动 `docker compose exec` 两条命令，是「一条命令部署」
# 的最后一道障碍，现由入口脚本自动完成。celery 等非 HTTP 进程不重复灌种子。
set -e

if [ "${SKIP_MIGRATE:-0}" != "1" ]; then
  echo "[entrypoint] 应用数据库迁移：alembic upgrade head"
  alembic upgrade head || echo "[entrypoint] 迁移未成功，交由应用内 lifespan 重试"
fi

case "${1:-}" in
  uvicorn*)
    if [ "${SEED_ON_STARTUP:-1}" = "1" ]; then
      echo "[entrypoint] 灌入种子数据（幂等，已存在则跳过）"
      python -m cenkor_admin.scripts.seed || echo "[entrypoint] seed 未成功，不影响服务启动"
    fi
    ;;
esac

exec "$@"
