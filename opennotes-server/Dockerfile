# syntax=docker/dockerfile:1.6

# Pre-built uv binary source — multi-arch
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS uv-source

# Base: minimal slim python with uv binary, no build tools
FROM python:3.11-slim AS base
WORKDIR /app
COPY --from=uv-source /usr/local/bin/uv /usr/local/bin/uv

# Builder: adds compile toolchain. Runtime stages will NOT inherit from this.
FROM base AS builder
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
       build-essential \
       git \
       curl \
  && rm -rf /var/lib/apt/lists/*

# ML deps layer — separated for cache stability
# Only rebuilt when ml-requirements.txt changes; app dependency changes do not bust this layer
FROM builder AS ml-deps
COPY opennotes-server/ml-requirements.txt ./ml-requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system \
      --index-url https://download.pytorch.org/whl/cpu \
      --extra-index-url https://pypi.org/simple \
      -r ml-requirements.txt

# App deps (production) — splits from ml-deps so dev-only changes don't bust prod cache
FROM ml-deps AS app-deps-prod
COPY opennotes-server/pyproject.toml opennotes-server/uv.lock opennotes-server/README.md opennotes-server/alembic.ini ./
COPY opennotes-server/src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --format requirements-txt --locked --extra scoring --no-hashes -o /tmp/requirements.txt \
 && uv pip install --system -r /tmp/requirements.txt \
 && uv pip install --system --no-deps -e .

# App deps (development) — adds dev extras
FROM ml-deps AS app-deps-dev
COPY opennotes-server/pyproject.toml opennotes-server/uv.lock opennotes-server/README.md opennotes-server/alembic.ini ./
COPY opennotes-server/src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --format requirements-txt --locked --extra scoring --extra dev --no-hashes -o /tmp/requirements.txt \
 && uv pip install --system -r /tmp/requirements.txt \
 && uv pip install --system --no-deps -e .

# Runtime base: clean slim + uv binary only — NO apt build tools
FROM python:3.11-slim AS runtime-base
WORKDIR /app
COPY --from=uv-source /usr/local/bin/uv /usr/local/bin/uv

# Production runtime
FROM runtime-base AS production
COPY --from=app-deps-prod /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=app-deps-prod /usr/local/bin /usr/local/bin
COPY --from=app-deps-prod /app/src /app/src
COPY --from=app-deps-prod /app/alembic.ini /app/alembic.ini
COPY opennotes-server/alembic/ ./alembic/
COPY opennotes-server/scripts/ ./scripts/
COPY opennotes-server/docker-entrypoint.sh ./
COPY communitynotes/scoring/src/ /communitynotes/scoring/src/
COPY opennotes-server/data/flashpoints/optimized_detector.json ./data/flashpoints/optimized_detector.json
RUN chmod +x docker-entrypoint.sh

ENV RUN_MODE=server
ARG VCS_REF=""
ARG BUILD_DATE=""
ARG VERSION=""
ENV VCS_REF=${VCS_REF} BUILD_DATE=${BUILD_DATE} BUILD_VERSION=${VERSION}
EXPOSE 8000
CMD ["./docker-entrypoint.sh"]

# Development runtime
FROM runtime-base AS development
COPY --from=app-deps-dev /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=app-deps-dev /usr/local/bin /usr/local/bin
COPY --from=app-deps-dev /app/src /app/src
COPY --from=app-deps-dev /app/alembic.ini /app/alembic.ini
COPY opennotes-server/alembic/ ./alembic/
COPY opennotes-server/scripts/ ./scripts/
COPY opennotes-server/docker-entrypoint.sh ./
COPY communitynotes/scoring/src/ /communitynotes/scoring/src/
COPY opennotes-server/data/flashpoints/optimized_detector.json ./data/flashpoints/optimized_detector.json
RUN chmod +x docker-entrypoint.sh

ENV RUN_MODE=server
ARG VCS_REF=""
ARG BUILD_DATE=""
ARG VERSION=""
ENV VCS_REF=${VCS_REF} BUILD_DATE=${BUILD_DATE} BUILD_VERSION=${VERSION}
EXPOSE 8000
CMD ["./docker-entrypoint.sh"]
