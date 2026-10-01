# Cenkor Admin · 全栈后端镜像
#   说明：与现有 backend/Dockerfile（dev 硬编码依赖）解耦的独立生产镜像，
#   用 requirements.txt（与宝塔一致）装依赖，减少镜像体积 + 非 root 安全
#   用法见 docker-compose.fullstack.yml
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# ---- 镜像源（默认官方，可用 --build-arg 覆盖）----
#   ⚠️ 不要硬编码单一镜像站：某些网络环境下特定镜像站会直接不可达
#   （实测某海外机器访问清华 PyPI 的 IPv4 就完全超时 → pip 报 Network is unreachable）。
#   中国大陆加速可传：
#     --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
#     --build-arg APT_MIRROR=mirrors.aliyun.com
ARG APT_MIRROR=deb.debian.org
ARG PIP_INDEX_URL=https://pypi.org/simple

# 系统依赖：asyncpg / psycopg2 编译 + 健康检查 curl
RUN if [ "$APT_MIRROR" != "deb.debian.org" ]; then \
      sed -i "s@deb.debian.org@${APT_MIRROR}@g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
      sed -i "s@deb.debian.org@${APT_MIRROR}@g" /etc/apt/sources.list 2>/dev/null || true; \
    fi; \
    apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖（利用构建缓存）；requirements.txt 由 pyproject.toml 同步
COPY backend/requirements.txt ./
RUN pip install --upgrade pip --index-url "${PIP_INDEX_URL}" && \
    pip install -r requirements.txt --index-url "${PIP_INDEX_URL}"

# 业务代码 + 迁移（启动时 lifespan 会自动 alembic upgrade head）
COPY backend/src ./src
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic

# 容器入口：启动前自动迁移 + 首次自动灌种子数据（免去手动 exec 两条命令）
COPY docker/fullstack/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# 非 root 运行（reduce 权限面）
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# start-period 放宽到 60s：入口脚本要先跑迁移与种子数据，再拉起 uvicorn
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# 生产入口由 compose command 覆盖（uvicorn / celery）
CMD ["uvicorn", "cenkor_admin.main:app", "--host", "0.0.0.0", "--port", "8000"]