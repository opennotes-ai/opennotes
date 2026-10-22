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

# Refresh the Arrow repository signer bundled by the base image. This is the
# official package linked by https://arrow.apache.org/install/, pinned so a
# changed download fails closed. Keep the existing Signed-By scope and keys.
RUN wget -q https://packages.apache.org/artifactory/arrow/debian/apache-arrow-apt-source-latest-trixie.deb \
        -O /tmp/apache-arrow-apt-source.deb \
    && echo "3b3afc167b6195211c302d4b1d49ef5fc628d1ff14c4ea50e518d9b8212c67d5  /tmp/apache-arrow-apt-source.deb" | sha256sum -c - \
    && dpkg-deb -x /tmp/apache-arrow-apt-source.deb /tmp/arrow-source \
    && mkdir -m 700 /tmp/arrow-keyring \
    && gpg --homedir /tmp/arrow-keyring --batch --import /tmp/arrow-source/usr/share/keyrings/apache-arrow-apt-source.asc \
    && gpg --homedir /tmp/arrow-keyring --batch --with-colons --fingerprint 7BD1A9A50E4F701BCBFD90EF9E922B2D60E9FD1C > /tmp/arrow-fingerprint \
    && grep -qx 'fpr:::::::::7BD1A9A50E4F701BCBFD90EF9E922B2D60E9FD1C:' /tmp/arrow-fingerprint \
    && gpg --homedir /tmp/arrow-keyring --batch --armor --export 7BD1A9A50E4F701BCBFD90EF9E922B2D60E9FD1C >> /usr/share/keyrings/apache-arrow-apt-source.asc \
    && rm -rf /tmp/apache-arrow-apt-source.deb /tmp/arrow-source /tmp/arrow-keyring /tmp/arrow-fingerprint

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
