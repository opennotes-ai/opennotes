# Production Discourse image for GCE deployment (linux/amd64)
#
# Build context: opennotes-discourse/ repository root
#   docker build -f docker/production/Dockerfile -t discourse-production .

ARG RUBY_VERSION=3.4.9
ARG DEBIAN_RELEASE=bookworm
ARG NODE_MAJOR=22
ARG DISCOURSE_VERSION=main

FROM ruby:${RUBY_VERSION}-slim-${DEBIAN_RELEASE}

ARG DEBIAN_RELEASE
ARG NODE_MAJOR
ARG DISCOURSE_VERSION
ENV RAILS_ENV=production \
    DISCOURSE_SERVE_STATIC_ASSETS=true \
    LC_ALL=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    LANGUAGE=en_US.UTF-8

RUN groupadd --gid 106 redis && \
    useradd --uid 103 --gid 106 --home /var/lib/redis --shell /usr/sbin/nologin redis && \
    groupadd --gid 1000 discourse && \
    useradd --uid 1000 --gid 1000 -m --shell /bin/bash discourse

RUN echo "deb http://deb.debian.org/debian ${DEBIAN_RELEASE}-backports main" \
      > /etc/apt/sources.list.d/${DEBIAN_RELEASE}-backports.list && \
    apt-get -y update && DEBIAN_FRONTEND=noninteractive apt-get -y install \
    gnupg sudo curl wget git locales ca-certificates \
    build-essential cmake g++ pkg-config autoconf patch \
    libxslt-dev libcurl4-openssl-dev libssl-dev libyaml-dev libtool \
    libpcre3 libpcre3-dev zlib1g zlib1g-dev libxml2-dev libreadline-dev \
    libpq-dev \
    gawk psmisc brotli libunwind-dev \
    pngcrush pngquant poppler-utils \
    imagemagick \
    ghostscript libjbig0 libtiff6 libpng16-16 libfontconfig1 \
    libwebpdemux2 libwebpmux3 libxext6 librsvg2-2 libgomp1 \
    fonts-urw-base35 \
    runit socat \
    libjemalloc-dev libjemalloc2 \
    && rm -rf /var/lib/apt/lists/*

RUN sed -i "s/^# en_US.UTF-8/en_US.UTF-8/" /etc/locale.gen && locale-gen

RUN apt-get -y update && DEBIAN_FRONTEND=noninteractive apt-get -y install \
    redis-server redis-tools \
    && rm -rf /var/lib/apt/lists/*

RUN curl --silent --location https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - && \
    apt-get -y update && DEBIAN_FRONTEND=noninteractive apt-get -y install nodejs && \
    npm install -g pnpm@10 && \
    rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/convert /usr/local/bin/magick

RUN ln -sf /usr/lib/$(dpkg --print-architecture)-linux-gnu/libjemalloc.so.2 /usr/lib/libjemalloc.so
ENV RUBY_ALLOCATOR=/usr/lib/libjemalloc.so

RUN gem install pups --force && \
    mkdir -p /pups/bin && \
    ln -s /usr/local/bin/pups /pups/bin/pups

RUN echo "discourse ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/discourse && \
    chmod 0440 /etc/sudoers.d/discourse

WORKDIR /var/www/discourse
RUN git clone https://github.com/discourse/discourse . --depth 1 --branch ${DISCOURSE_VERSION}

RUN bundle config set --local without "development test" && \
    bundle install --jobs $(nproc) && \
    rm -rf /usr/local/bundle/cache/*

RUN if [ -f yarn.lock ]; then yarn install --production; else CI=1 pnpm install --frozen-lockfile; fi

COPY plugin/ /var/www/discourse/plugins/discourse-opennotes/

RUN echo 'export BUNDLE_APP_CONFIG=/usr/local/bundle' >> /etc/profile.d/bundle.sh && \
    echo 'BUNDLE_APP_CONFIG=/usr/local/bundle' >> /etc/environment

RUN mkdir -p /etc/runit/1.d /etc/service /shared /var/discourse/shared/redis

RUN mkdir -p /etc/service/redis /var/log/redis && \
    printf '#!/bin/bash\nexec chpst -u redis redis-server --port 6379 --loglevel notice --dir /var/discourse/shared/redis\n' \
      > /etc/service/redis/run && \
    chmod +x /etc/service/redis/run && \
    mkdir -p /etc/service/redis/log && \
    printf '#!/bin/bash\nsvlogd /var/log/redis\n' > /etc/service/redis/log/run && \
    chmod +x /etc/service/redis/log/run

RUN mkdir -p /etc/service/rails /var/log/rails && \
    printf '#!/bin/bash\nexport BUNDLE_APP_CONFIG=/usr/local/bundle\nexport HOME=/home/discourse\nexport PGSSLCERT=""\nexport PGSSLKEY=""\ncd /var/www/discourse\nexec chpst -u discourse bundle exec pitchfork -E production -c config/pitchfork.conf.rb\n' \
      > /etc/service/rails/run && \
    chmod +x /etc/service/rails/run && \
    mkdir -p /etc/service/rails/log && \
    printf '#!/bin/bash\nsvlogd /var/log/rails\n' > /etc/service/rails/log/run && \
    chmod +x /etc/service/rails/log/run

RUN mkdir -p /etc/service/sidekiq /var/log/sidekiq && \
    printf '#!/bin/bash\nexport BUNDLE_APP_CONFIG=/usr/local/bundle\nexport HOME=/home/discourse\nexport PGSSLCERT=""\nexport PGSSLKEY=""\ncd /var/www/discourse\nexec chpst -u discourse bundle exec sidekiq\n' \
      > /etc/service/sidekiq/run && \
    chmod +x /etc/service/sidekiq/run && \
    mkdir -p /etc/service/sidekiq/log && \
    printf '#!/bin/bash\nsvlogd /var/log/sidekiq\n' > /etc/service/sidekiq/log/run && \
    chmod +x /etc/service/sidekiq/log/run

RUN SKIP_DB_AND_REDIS=1 SECRET_KEY_BASE=precompile_placeholder \
    bundle exec rake assets:precompile && \
    chown -R discourse:discourse /var/www/discourse

COPY docker/production/boot /sbin/boot
RUN chmod +x /sbin/boot

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD curl -f http://localhost:3000/srv/status || exit 1

CMD ["/sbin/boot"]
