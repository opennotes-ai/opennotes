# syntax=docker/dockerfile:1.4
# =============================================================================
# Layer Caching Strategy for Python ML Dependencies
# =============================================================================
# REQUIRES: Docker BuildKit (enabled by default in Docker 23.0+)
# For older Docker versions, set: DOCKER_BUILDKIT=1
# =============================================================================
# This Dockerfile uses a multi-stage build optimized for Docker layer caching:
#
# 1. base:     Python + system deps + Rust (for cryptography) + uv
# 2. ml-deps:  Heavy ML packages (torch, transformers, etc.) - ~3GB, rarely change
# 3. dev/prod: App dependencies + source code - changes frequently
#
# Benefits:
# - ML layer cached across builds when only app deps change
# - BuildKit cache mounts for uv/pip caches
# - Faster CI/CD builds (skip ~3GB layer most of the time)
# =============================================================================

FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl build-essential && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

RUN pip install --no-cache-dir uv

COPY opennotes-server/pyproject.toml opennotes-server/README.md opennotes-server/alembic.ini ./

FROM base AS ml-deps

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    uv pip install --system --group ml

FROM ml-deps AS development

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    uv pip install --system -e ".[scoring,dev]"

COPY opennotes-server/src/ ./src/
COPY opennotes-server/alembic/ ./alembic/
COPY opennotes-server/scripts/ ./scripts/
COPY opennotes-server/docker-entrypoint.sh ./
COPY communitynotes/scoring/src/ /communitynotes/scoring/src/

RUN chmod +x docker-entrypoint.sh scripts/run_migrations_with_lock.py

# RUN_MODE controls startup: server (default), worker, or both
ENV RUN_MODE=server

EXPOSE 8000

CMD ["./docker-entrypoint.sh"]

FROM ml-deps AS production

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    uv pip install --system -e ".[scoring]"

COPY opennotes-server/src/ ./src/
COPY opennotes-server/alembic/ ./alembic/
COPY opennotes-server/scripts/ ./scripts/
COPY opennotes-server/docker-entrypoint.sh ./
COPY communitynotes/scoring/src/ /communitynotes/scoring/src/

RUN chmod +x docker-entrypoint.sh scripts/run_migrations_with_lock.py

# RUN_MODE controls startup: server (default), worker, or both
ENV RUN_MODE=server

EXPOSE 8000

CMD ["./docker-entrypoint.sh"]
