FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl build-essential && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

RUN pip install --no-cache-dir uv

COPY opennotes-server/pyproject.toml opennotes-server/README.md opennotes-server/alembic.ini ./

FROM base AS development

RUN uv pip install --system -e ".[scoring,dev]"

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

FROM base AS production

RUN uv pip install --system -e ".[scoring]"

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
