#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

EXPECTED_SYMLINK_TARGET="../../../plugin"

echo "==> OpenNotes Discourse development bootstrap"

# Step 1: Clone Discourse
if [ ! -d "docker/.discourse" ]; then
  echo "==> Cloning discourse/discourse into docker/.discourse..."
  git clone https://github.com/discourse/discourse.git docker/.discourse
else
  echo "==> docker/.discourse already exists, skipping clone"
fi

# Step 2: Create/validate plugin symlink
SYMLINK_TARGET="docker/.discourse/plugins/discourse-opennotes"
mkdir -p docker/.discourse/plugins

if [ -L "$SYMLINK_TARGET" ]; then
  CURRENT_TARGET=$(readlink "$SYMLINK_TARGET")
  if [ "$CURRENT_TARGET" != "$EXPECTED_SYMLINK_TARGET" ]; then
    echo "==> Fixing stale plugin symlink ($CURRENT_TARGET -> $EXPECTED_SYMLINK_TARGET)..."
    ln -sfn "$EXPECTED_SYMLINK_TARGET" "$SYMLINK_TARGET"
  else
    echo "==> Plugin symlink is correct"
  fi
elif [ -e "$SYMLINK_TARGET" ]; then
  echo "Error: $SYMLINK_TARGET exists but is not a symlink. Remove it and re-run."
  exit 1
else
  echo "==> Creating plugin symlink..."
  ln -sfn "$EXPECTED_SYMLINK_TARGET" "$SYMLINK_TARGET"
fi

# Step 3: Build native ARM64 image if on Apple Silicon
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then
  if ! docker image inspect discourse/discourse_dev:release > /dev/null 2>&1; then
    echo "==> Apple Silicon detected. Building native ARM64 Discourse dev image..."
    echo "    (This takes ~5 minutes the first time, cached after)"
    docker build -t discourse/discourse_dev:release "$SCRIPT_DIR/arm64"
  else
    echo "==> Native ARM64 Discourse dev image already built"
  fi
fi

# Step 4: Boot container
if docker ps -q -f name=discourse_dev | grep -q .; then
  echo "==> discourse_dev container already running"
else
  echo "==> Booting Discourse dev container..."
  cd docker/.discourse
  d/boot_dev 2>&1 || true
  cd "$SCRIPT_DIR/.."

  # Verify container is actually running
  sleep 3
  if ! docker ps -q -f name=discourse_dev | grep -q .; then
    echo "Error: discourse_dev container failed to start."
    echo "Check Docker logs: docker logs discourse_dev"
    exit 1
  fi
  echo "==> Container is running"
fi

# Ensure host.docker.internal resolves inside container
# (d/boot_dev doesn't support DOCKER_ARGS for --add-host)
if ! docker exec discourse_dev getent hosts host.docker.internal > /dev/null 2>&1; then
  GATEWAY_IP=$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}')
  docker exec discourse_dev bash -c "echo '$GATEWAY_IP host.docker.internal' >> /etc/hosts"
  echo "==> Added host.docker.internal -> $GATEWAY_IP"
fi

# Step 4: Install dependencies
echo "==> Installing Ruby gems..."
docker exec -u discourse discourse_dev bash -c "cd /src && bundle install"

echo "==> Installing JS dependencies..."
docker exec -u discourse discourse_dev bash -c "cd /src && pnpm install"

# Step 5: Database setup
echo "==> Running database migrations..."
docker exec -u discourse discourse_dev bash -c "cd /src && bundle exec rake db:create db:migrate" 2>&1 || \
  docker exec -u discourse discourse_dev bash -c "cd /src && bundle exec rake db:migrate"

# Step 6: Seed admin user
echo "==> Seeding admin user..."
SEED_ADMIN=$(mktemp)
cat > "$SEED_ADMIN" << 'RUBY'
SiteSetting.min_admin_password_length = 10
SiteSetting.min_password_length = 8
unless User.find_by(username: "admin")
  user = User.create!(
    username: "admin",
    email: "admin@opennotes.local",
    password: "opennotes-dev-password",
    active: true,
    approved: true,
    admin: true
  )
  user.activate
  user.grant_admin!
  puts "Admin user created: admin@opennotes.local"
else
  puts "Admin user already exists"
end
RUBY
docker cp "$SEED_ADMIN" discourse_dev:/src/tmp/seed_admin.rb
rm "$SEED_ADMIN"
docker exec -u discourse discourse_dev bash -c "cd /src && bundle exec rails runner tmp/seed_admin.rb"

# Step 7: Provision API key for automation
echo "==> Provisioning API key..."
API_KEY_SCRIPT=$(mktemp)
cat > "$API_KEY_SCRIPT" << 'RUBY'
admin = User.find_by(username: "admin")
existing = ApiKey.where(user_id: admin.id).first
if existing
  puts existing.key
else
  key = ApiKey.create!(user_id: admin.id, created_by_id: admin.id, description: "Bootstrap dev key")
  puts key.key
end
RUBY
docker cp "$API_KEY_SCRIPT" discourse_dev:/src/tmp/api_key.rb
rm "$API_KEY_SCRIPT"
API_KEY=$(docker exec -u discourse discourse_dev bash -c "cd /src && bundle exec rails runner tmp/api_key.rb" 2>/dev/null | tail -1)
echo "$API_KEY" > docker/.discourse-api-key
echo "==> API key saved to docker/.discourse-api-key"

# Step 8: Start Rails + Ember (if not already running)
if docker exec discourse_dev bash -c "pgrep -f 'rails s' > /dev/null 2>&1"; then
  echo "==> Rails server already running"
else
  echo "==> Starting Rails server..."
  docker exec -d -u discourse discourse_dev bash -c "cd /src && bundle exec rails s -b 0.0.0.0 -p 3000 > /tmp/rails.log 2>&1"
fi

if docker exec discourse_dev bash -c "pgrep -f 'ember-cli' > /dev/null 2>&1"; then
  echo "==> Ember CLI already running"
else
  echo "==> Starting Ember CLI..."
  docker exec -d -u discourse discourse_dev bash -c "cd /src && bin/ember-cli -p 4200 > /tmp/ember.log 2>&1"
fi

# Step 9: Wait for ready
echo "==> Waiting for Discourse to become ready..."
docker/scripts/wait-for-discourse.sh

echo ""
echo "==> Bootstrap complete!"
echo "    Discourse: http://localhost:4200"
echo "    Admin:     admin@opennotes.local"
echo "    API key:   $(cat docker/.discourse-api-key)"
