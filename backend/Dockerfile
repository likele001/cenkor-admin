FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 系统依赖（asyncpg 编译需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖（利用 Docker 缓存）
COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install \
    "fastapi>=0.110.0" \
    "uvicorn[standard]>=0.27.0" \
    "pydantic>=2.6.0" \
    "pydantic-settings>=2.2.0" \
    "pydantic-extra-types>=2.5.0" \
    "sqlalchemy[asyncio]>=2.0.25" \
    "alembic>=1.13.0" \
    "asyncpg>=0.29.0" \
    "aiomysql>=0.2.0" \
    "psycopg2-binary>=2.9.9" \
    "redis>=5.0.0" \
    "celery[redis]>=5.3.0" \
    "python-jose[cryptography]>=3.3.0" \
    "passlib[bcrypt]>=1.7.4" \
    "bcrypt>=3.2.0,<4.0" \
    "python-dotenv>=1.0.0" \
    "httpx>=0.27.0" \
    "boto3>=1.34.0" \
    "aiobotocore>=2.5.0" \
    "structlog>=24.1.0" \
    "loguru>=0.7.2" \
    "email-validator>=2.1.0" \
    "python-slugify>=8.0.0" \
    "python-multipart>=0.0.9" \
    "Pillow>=10.0.0"

# 代码（开发模式挂载）
COPY src ./src

ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["uvicorn", "cenkor_admin.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
