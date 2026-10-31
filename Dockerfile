# JevRouter API 镜像。
#
# 这是服务端：凭证（JEV_API_KEY / LLM_API_KEY）只在这个进程里，镜像本身不携带任何密钥。
# 运行示例见 README 的「容器运行」一节。
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先只装依赖：代码改动时这一层仍然命中缓存。
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY jev_router ./jev_router
COPY apps ./apps

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# 默认只监听容器内的 8000；对外暴露哪些端口由编排层决定。
EXPOSE 8000

# 数据库与工作区都落在 /app/data，方便挂载卷持久化。
ENV JEV_DATABASE_PATH=/app/data/traces.db \
    JEV_WORKSPACE_ROOT=/app/data/workspace

RUN mkdir -p /app/data

CMD ["uvicorn", "apps.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
