# discourse_dev for ARM64 (Apple Silicon)
#
# Single-stage build that produces an image compatible with Discourse's
# d/boot_dev workflow, running natively on ARM64 instead of under x86_64
# emulation.
#
# Build (~5 min first time, cached after):
#   docker build -t discourse/discourse_dev:arm64 docker/arm64
#
# Then bootstrap normally:
#   mise run discourse:bootstrap
#
# Based on: https://github.com/discourse/discourse_docker/blob/main/image/

ARG RUBY_VERSION=3.4.9
ARG DEBIAN_RELEASE=bookworm
ARG PG_MAJOR=15
ARG NODE_MAJOR=22

FROM ruby:${RUBY_VERSION}-slim-${DEBIAN_RELEASE}

ARG DEBIAN_RELEASE
ARG PG_MAJOR
ARG NODE_MAJOR
ENV PG_MAJOR=${PG_MAJOR} \
    RAILS_ENV=development \
    LC_ALL=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    LANGUAGE=en_US.UTF-8

# --- Users & groups (match upstream UIDs) ---
RUN groupadd --gid 104 postgres && \
    useradd --uid 101 --gid 104 --home /var/lib/postgresql --shell /bin/bash postgres && \
    groupadd --gid 106 redis && \
    useradd --uid 103 --gid 106 --home /var/lib/redis --shell /usr/sbin/nologin redis && \
    groupadd --gid 1000 discourse && \
    useradd --uid 1000 --gid 1000 -m --shell /bin/bash discourse

# --- Base packages ---
RUN echo "deb http://deb.debian.org/debian ${DEBIAN_RELEASE}-backports main" \
      > /etc/apt/sources.list.d/${DEBIAN_RELEASE}-backports.list && \
    apt-get -y update && DEBIAN_FRONTEND=noninteractive apt-get -y install \
    gnupg sudo curl wget git locales ca-certificates \
    build-essential cmake g++ pkg-config autoconf patch \
    libxslt-dev libcurl4-openssl-dev libssl-dev libyaml-dev libtool \
    libpcre3 libpcre3-dev zlib1g zlib1g-dev libxml2-dev libreadline-dev \
    libpq-dev libsqlite3-dev \
    gawk parallel psmisc whois brotli libunwind-dev \
    pngcrush pngquant ripgrep poppler-utils \
    ghostscript libjbig0 libtiff6 libpng16-16 libfontconfig1 \
    libwebpdemux2 libwebpmux3 libxext6 librsvg2-2 libgomp1 \
    fonts-urw-base35 \
    rsyslog logrotate cron ssh-client less anacron \
    runit socat \
    libjemalloc-dev libjemalloc2 \
    && rm -rf /var/lib/apt/lists/*

# --- Locale ---
RUN sed -i "s/^# en_US.UTF-8/en_US.UTF-8/" /etc/locale.gen && locale-gen

# --- PostgreSQL ---
RUN install -d /usr/share/postgresql-common/pgdg && \
    curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc --fail \
      https://www.postgresql.org/media/keys/ACCC4CF8.asc && \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${DEBIAN_RELEASE}-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list && \
    apt-get -y update && DEBIAN_FRONTEND=noninteractive apt-get -y install \
    postgresql-${PG_MAJOR} postgresql-contrib-${PG_MAJOR} postgresql-${PG_MAJOR}-pgvector \
    && rm -rf /var/lib/apt/lists/*

# --- Redis ---
RUN apt-get -y update && DEBIAN_FRONTEND=noninteractive apt-get -y install \
    redis-server redis-tools \
    && rm -rf /var/lib/apt/lists/*

# --- Node.js + pnpm ---
RUN curl --silent --location https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - && \
    apt-get -y update && DEBIAN_FRONTEND=noninteractive apt-get -y install nodejs && \
    npm install -g pnpm@10 && \
    rm -rf /var/lib/apt/lists/*

# --- jemalloc ---
RUN ln -sf /usr/lib/$(dpkg --print-architecture)-linux-gnu/libjemalloc.so.2 /usr/lib/libjemalloc.so
ENV RUBY_ALLOCATOR=/usr/lib/libjemalloc.so

# --- MailHog (ARM-aware) ---
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "arm64" ]; then MH_BIN="MailHog_linux_arm"; \
    else MH_BIN="MailHog_linux_amd64"; fi && \
    wget -qO /usr/local/bin/mailhog \
      "https://github.com/mailhog/MailHog/releases/download/v1.0.1/${MH_BIN}" && \
    chmod +x /usr/local/bin/mailhog

# --- Pups (Discourse config tool) ---
RUN gem install pups --force && \
    mkdir -p /pups/bin && \
    ln -s /usr/local/bin/pups /pubs/bin/pups 2>/dev/null; \
    ln -s /usr/local/bin/pups /pups/bin/pups

# --- Discourse sudo permissions ---
RUN echo "discourse ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/discourse && \
    chmod 0440 /etc/sudoers.d/discourse

# --- Bundle config ---
RUN sudo -u discourse bundle config set --global path /home/discourse/.bundle/gems
RUN echo 'PATH="$(ruby -r rubygems -e "puts Gem.user_dir")/bin:$PATH"' >> /home/discourse/.profile

# --- runit services ---
RUN mkdir -p /etc/runit/1.d /etc/runit/3.d /etc/service /shared

# PostgreSQL runit service
RUN mkdir -p /etc/service/postgres /var/log/postgres && \
    printf '#!/bin/bash\nexec chpst -u postgres /usr/lib/postgresql/%s/bin/postmaster -D /etc/postgresql/%s/main\n' \
      "${PG_MAJOR}" "${PG_MAJOR}" > /etc/service/postgres/run && \
    chmod +x /etc/service/postgres/run && \
    printf '#!/bin/bash\nsvlogd /var/log/postgres\n' > /etc/service/postgres/log/run 2>/dev/null; \
    mkdir -p /etc/service/postgres/log && \
    printf '#!/bin/bash\nsvlogd /var/log/postgres\n' > /etc/service/postgres/log/run && \
    chmod +x /etc/service/postgres/log/run

# Redis runit service
RUN mkdir -p /etc/service/redis /var/log/redis && \
    printf '#!/bin/bash\nexec chpst -u redis redis-server --port 6379 --loglevel notice\n' \
      > /etc/service/redis/run && \
    chmod +x /etc/service/redis/run && \
    mkdir -p /etc/service/redis/log && \
    printf '#!/bin/bash\nsvlogd /var/log/redis\n' > /etc/service/redis/log/run && \
    chmod +x /etc/service/redis/log/run

# Cron + rsyslog runit services
RUN mkdir -p /etc/service/cron && \
    printf '#!/bin/bash\nexec cron -f\n' > /etc/service/cron/run && \
    chmod +x /etc/service/cron/run && \
    mkdir -p /etc/service/rsyslog && \
    printf '#!/bin/bash\nexec rsyslogd -n\n' > /etc/service/rsyslog/run && \
    chmod +x /etc/service/rsyslog/run

# --- PostgreSQL init ---
RUN pg_dropcluster ${PG_MAJOR} main 2>/dev/null; \
    pg_createcluster ${PG_MAJOR} main --start && \
    su postgres -c "psql -c \"CREATE ROLE discourse WITH LOGIN SUPERUSER PASSWORD 'discourse';\"" && \
    su postgres -c "createdb discourse" && \
    su postgres -c "createdb discourse_test" && \
    pg_ctlcluster ${PG_MAJOR} main stop && \
    mv /var/lib/postgresql/${PG_MAJOR}/main /shared/postgres_data_orig

# ensure-database: restore postgres data on boot if volume is empty
COPY ensure-database /etc/runit/1.d/ensure-database
RUN chmod +x /etc/runit/1.d/ensure-database

# --- Boot ---
RUN sed -i.bak 's/$ModLoad imklog/#$ModLoad imklog/' /etc/rsyslog.conf 2>/dev/null; \
    sed -i.bak 's/module(load="imklog")/#module(load="imklog")/' /etc/rsyslog.conf 2>/dev/null; true

COPY boot /sbin/boot
RUN chmod +x /sbin/boot

# --- Pre-warm bundle + pnpm caches ---
USER discourse
RUN git clone https://github.com/discourse/discourse /tmp/discourse-clone --depth 1 && \
    cd /tmp/discourse-clone && \
    bundle install && \
    rm -rf /home/discourse/.bundle/gems/ruby/*/cache/* && \
    (if [ -f yarn.lock ]; then yarn install; else CI=1 pnpm install; fi) && \
    cd / && rm -rf /tmp/discourse-clone

USER root

CMD ["/sbin/boot"]
