# PostgreSQL with pgvector, pgroonga, and pg_cron extensions
# This image combines extensions for hybrid search and maintenance:
# - pgvector: Vector similarity search using HNSW indexes
# - pgroonga: Full-text search with TF-IDF scoring via Groonga
# - pg_cron: Job scheduler for maintenance tasks (e.g., materialized view refresh)
#
# Build: docker build -t opennotes/postgres:18-pgvector-pgroonga docker/postgres
# Usage: Replace pgvector/pgvector:pg18 with opennotes/postgres:18-pgvector-pgroonga
#
# Based on PGroonga's official Debian image and adds pgvector + pg_cron on top.
# PGroonga Debian images include the Groonga C library and PostgreSQL integration.

ARG PGROONGA_VERSION=4.0.5
ARG PG_MAJOR=18

FROM groonga/pgroonga:${PGROONGA_VERSION}-debian-${PG_MAJOR}

ARG PG_MAJOR

# Install build dependencies for pgvector
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    postgresql-server-dev-${PG_MAJOR} \
    && rm -rf /var/lib/apt/lists/*

# Clone and build pgvector from source
# Using v0.8.1 which includes PostgreSQL 18 support (vacuum_delay_point API change)
ARG PGVECTOR_VERSION=0.8.1
RUN cd /tmp \
    && git clone --branch v${PGVECTOR_VERSION} https://github.com/pgvector/pgvector.git \
    && cd pgvector \
    && make OPTFLAGS="" \
    && make install \
    && cd / \
    && rm -rf /tmp/pgvector

# Clean up build dependencies to reduce image size
RUN apt-get purge -y build-essential git postgresql-server-dev-${PG_MAJOR} \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Install pg_cron for scheduled job support
# pg_cron requires shared_preload_libraries configuration (done at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-${PG_MAJOR}-cron \
    && rm -rf /var/lib/apt/lists/*

# Verify extensions are available
RUN pg_config --version && ls -la $(pg_config --sharedir)/extension/ | grep -E "(pgroonga|vector|pg_cron)"

# Default entrypoint from base image handles PostgreSQL startup
