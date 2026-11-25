# Cenkor Admin · 全栈后端镜像
#   说明：与现有 backend/Dockerfile（dev 硬编码依赖）解耦的独立生产镜像，
#   用 requirements.txt（与宝塔一致）装依赖，减少镜像体积 + 非 root 安全
#   用法见 docker-compose.fullstack.yml
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src
# ⚠️ 不要加 PIP_NO_CACHE_DIR=1：它会让下面的 cache mount 完全失效，
#    每次重建都要重下全部 wheel（WSL / 国内网络下单次 20 分钟以上）。
#    wheel 缓存留在构建机的 cache mount 里，不进最终镜像层，体积不受影响。

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
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    if [ "$APT_MIRROR" != "deb.debian.org" ]; then \
      sed -i "s@deb.debian.org@${APT_MIRROR}@g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
      sed -i "s@deb.debian.org@${APT_MIRROR}@g" /etc/apt/sources.list 2>/dev/null || true; \
    fi; \
    apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖（利用构建缓存）；requirements.txt 由 pyproject.toml 同步
COPY backend/requirements.txt ./
# ---- 用 uv 装依赖，不用 pip ----
#   pip 的下载是串行的（一个包装完才下一个），40 个直接依赖在慢网下
#   实测 1335s —— 换国内镜像也没用，因为瓶颈是"串行 × 单文件速度"。
#   uv 默认并发下载，同等带宽下通常能压到几分之一。
#
#   · --system           直接装进容器的系统 Python（容器内不需要 venv）
#   · UV_LINK_MODE=copy  必须设：cache mount 与 site-packages 跨文件系统，
#                        默认的硬链接会逐条失败告警并退回全量复制，反而更慢
#   · UV_HTTP_TIMEOUT    慢网下单个大 wheel 容易超过默认超时
#   · 装完把 uv 本体卸掉：运行时用不到，别让镜像白背 30MB
#
#   依赖结果与 pip 逐包比对过：88 个包，包集合与版本零差异。
ENV UV_CACHE_DIR=/root/.cache/uv \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=120

RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --index-url "${PIP_INDEX_URL}" uv \
    && uv pip install --system -r requirements.txt --index-url "${PIP_INDEX_URL}" \
    && pip uninstall -y uv

# 业务代码 + 迁移（启动时 lifespan 会自动 alembic upgrade head）
COPY backend/src ./src

# 外置 App 的额外依赖（collect 的 parsel/trafilatura/feedparser 等）。
# 这些刻意不在主 requirements 里：只有装了对应 App 才需要。
# apps/ 不入 git —— CI 与客户 checkout 没有该目录，这里会自动跳过，
# 所以不会因为「文件不存在」让镜像构建失败。复用上面的 uv 缓存。
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    if ls src/apps/*/requirements.txt >/dev/null 2>&1; then \
      pip install --index-url "${PIP_INDEX_URL}" uv; \
      for f in src/apps/*/requirements.txt; do \
        echo ">>> App 额外依赖: $f"; \
        uv pip install --system -r "$f" --index-url "${PIP_INDEX_URL}" || exit 1; \
      done; \
      pip uninstall -y uv; \
    else \
      echo ">>> 无 apps 目录，跳过 App 额外依赖"; \
    fi

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