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

# 系统依赖：asyncpg / psycopg2 编译 + 健康检查 curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖（利用构建缓存）；requirements.txt 由 pyproject.toml 同步
COPY backend/requirements.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# 业务代码
COPY backend/src ./src

# 非 root 运行（reduce 权限面）
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# 生产入口由 compose command 覆盖（uvicorn / celery）
CMD ["uvicorn", "cenkor_admin.main:app", "--host", "0.0.0.0", "--port", "8000"]