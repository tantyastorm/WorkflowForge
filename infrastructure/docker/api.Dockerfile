FROM python:3.12.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_SYNC=1

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock alembic.ini ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY apps/scheduler/pyproject.toml apps/scheduler/pyproject.toml
COPY packages/application/pyproject.toml packages/application/pyproject.toml
COPY packages/contracts/pyproject.toml packages/contracts/pyproject.toml
COPY packages/domain/pyproject.toml packages/domain/pyproject.toml
COPY packages/infrastructure/pyproject.toml packages/infrastructure/pyproject.toml

RUN uv sync --frozen --all-packages --no-dev --no-install-workspace

COPY apps/api/src apps/api/src
COPY apps/worker/src apps/worker/src
COPY apps/scheduler/src apps/scheduler/src
COPY packages/application/src packages/application/src
COPY packages/contracts/src packages/contracts/src
COPY packages/domain/src packages/domain/src
COPY packages/infrastructure/src packages/infrastructure/src
COPY migrations migrations

RUN uv sync --frozen --all-packages --no-dev \
    && groupadd --system workflowforge \
    && useradd --system --gid workflowforge --home-dir /app --shell /usr/sbin/nologin workflowforge \
    && chown -R workflowforge:workflowforge /app

USER workflowforge

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "workflowforge_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
