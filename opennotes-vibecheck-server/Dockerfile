# syntax=docker/dockerfile:1.6

# Pre-built uv binary source — multi-arch
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS uv-source

# Base: minimal slim python with uv binary
FROM python:3.11-slim AS base
WORKDIR /app
COPY --from=uv-source /usr/local/bin/uv /usr/local/bin/uv

# Builder: adds compile toolchain for any wheels that need it
FROM base AS builder
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
       build-essential \
       git \
       curl \
  && rm -rf /var/lib/apt/lists/*

# App deps (production)
FROM builder AS app-deps
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -e .

# Runtime: clean slim python with uv binary and installed site-packages
FROM python:3.11-slim AS runtime
WORKDIR /app
COPY --from=uv-source /usr/local/bin/uv /usr/local/bin/uv
COPY --from=app-deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=app-deps /usr/local/bin /usr/local/bin
COPY --from=app-deps /app/src /app/src

RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
  && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system "yt-dlp==2026.3.17"

ARG VCS_REF=""
ARG BUILD_DATE=""
ARG VERSION=""
ENV VCS_REF=${VCS_REF} BUILD_DATE=${BUILD_DATE} BUILD_VERSION=${VERSION}

EXPOSE 8080
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
