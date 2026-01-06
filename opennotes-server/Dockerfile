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
# 2. ml-deps:  Heavy ML packages (torch, transformers, etc.) - CPU-only (~800MB)
#              ONLY changes when ml-requirements.txt changes
# 3. dev/prod: App dependencies + source code - changes frequently
#
# CPU-only PyTorch:
# - We use CPU-only PyTorch to reduce image size from ~7.5GB to ~2.5GB
# - CUDA/GPU libraries are NOT included (saves ~4.7GB)
# - If GPU support is needed, use --extra-index-url https://download.pytorch.org/whl/cu121
#
# Benefits:
# - ML layer cached across builds when only app deps change
# - pyproject.toml changes don't invalidate ML layer
# - BuildKit cache mounts for uv/pip caches
# - Faster CI/CD builds (skip ML layer most of the time)
# =============================================================================

FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl build-essential && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

RUN pip install --no-cache-dir uv

# =============================================================================
# ML Dependencies Layer
# =============================================================================
# This layer ONLY depends on ml-requirements.txt, not pyproject.toml
# Changes to pyproject.toml will NOT invalidate this layer
# Regenerate ml-requirements.txt with: uv export --only-group ml --no-hashes
# =============================================================================
FROM base AS ml-deps

COPY opennotes-server/ml-requirements.txt ./ml-requirements.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r ml-requirements.txt

# =============================================================================
# Development Stage
# =============================================================================
FROM ml-deps AS development

COPY opennotes-server/pyproject.toml opennotes-server/README.md opennotes-server/alembic.ini ./

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

# =============================================================================
# Production Stage
# =============================================================================
FROM ml-deps AS production

COPY opennotes-server/pyproject.toml opennotes-server/README.md opennotes-server/alembic.ini ./

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
