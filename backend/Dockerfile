# syntax=docker/dockerfile:1
# ↑ 启用 cache mount 需要 BuildKit 前端（Docker 23+ 默认开启 BuildKit）
#
# 这是**开发**镜像：依赖硬编码在此，代码靠 compose 卷挂载热更新。
# 生产镜像见 docker/fullstack/backend.Dockerfile（用 requirements.txt + uv）。

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
# ⚠️ 不要加 PIP_NO_CACHE_DIR=1：它会让下面的 pip cache mount 完全失效，
#    每次重建都要重下全部 wheel。fullstack 镜像实测过这个坑 ——
#    WSL/国内网络下 pip 阶段要 1335s，去掉缓存目录后 cache mount 才真正生效。
#    缓存留在构建机的 BuildKit 存储里，不进入镜像层，体积不受影响。

WORKDIR /app

# 系统依赖（asyncpg / psycopg2 编译需要）
# sharing=locked：并行构建同一镜像时串行访问缓存，避免互相踩坏
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 依赖统一从 requirements.txt 装 —— 与宝塔环境、生产镜像同一份清单。
#
# 这里以前是一份硬编码列表，独立演进后和 requirements 漂移了：
# 缺 Jinja2 / nh3 / pgvector / PyYAML，dev 镜像里 CMS 模板渲染、markdown 净化、
# 向量检索会直接 ImportError；反过来又多装了一个代码根本没用到的 boto3。
# 硬编码列表注定会再漂一次，所以干脆改成读同一份文件。
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# 代码（开发模式挂载）
COPY src ./src

# 外置 App 的额外依赖：每个 App 用自己的 requirements.txt 声明，
# 刻意不塞进主依赖（如 collect 需要 parsel/trafilatura/feedparser，
# 只有装了该 App 才有意义）。
#
# 放在 COPY src 之后：清单文件属于源码树。
# apps/ 不入 git —— CI 与客户环境的干净 checkout 里没有这个目录，
# 此时通配符不匹配，`[ -f ]` 判假直接跳过，不会让构建失败。
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    for f in src/apps/*/requirements.txt; do \
      [ -f "$f" ] || continue; \
      echo ">>> 安装 App 额外依赖: $f"; \
      pip install -r "$f" || exit 1; \
    done

ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["uvicorn", "cenkor_admin.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
