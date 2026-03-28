#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "==> OpenNotes Discourse development bootstrap"

if [ ! -d "docker/.discourse" ]; then
  echo "==> Cloning discourse/discourse into docker/.discourse..."
  git clone https://github.com/discourse/discourse.git docker/.discourse
else
  echo "==> docker/.discourse already exists, skipping clone"
fi

SYMLINK_TARGET="docker/.discourse/plugins/discourse-opennotes"
if [ ! -L "$SYMLINK_TARGET" ]; then
  echo "==> Creating plugin symlink..."
  mkdir -p docker/.discourse/plugins
  ln -sf ../../../plugin "$SYMLINK_TARGET"
else
  echo "==> Plugin symlink already exists"
fi

echo "==> Booting Discourse dev container..."
echo "    (This starts the container; d/boot_dev --init may require a TTY)"
cd docker/.discourse

# boot_dev starts the container. --init does first-time setup but needs TTY.
# We handle setup steps manually for non-interactive use.
if ! docker ps -q -f name=discourse_dev | grep -q .; then
  d/boot_dev 2>&1 || true
  sleep 5
fi
cd "$SCRIPT_DIR/.."

echo "==> Installing Ruby gems..."
docker exec -u discourse discourse_dev bash -c "cd /src && bundle install"

echo "==> Installing JS dependencies..."
docker exec -u discourse discourse_dev bash -c "cd /src && pnpm install"

echo "==> Running database migrations..."
docker exec -u discourse discourse_dev bash -c "cd /src && bundle exec rake db:create db:migrate" 2>&1 || \
  docker exec -u discourse discourse_dev bash -c "cd /src && bundle exec rake db:migrate"

echo "==> Seeding admin user..."
docker exec -u discourse discourse_dev bash -c 'cd /src && bundle exec rails runner "
  SiteSetting.min_admin_password_length = 10
  SiteSetting.min_password_length = 8
  unless User.find_by(username: \"admin\")
    user = User.create!(
      username: \"admin\",
      email: \"admin@opennotes.local\",
      password: \"opennotes-dev-password\",
      active: true,
      approved: true,
      admin: true
    )
    user.activate
    user.grant_admin!
    puts \"Admin user created: admin@opennotes.local / opennotes-dev-password\"
  else
    puts \"Admin user already exists\"
  end
"'

echo "==> Starting Rails server..."
docker exec -d -u discourse discourse_dev bash -c "cd /src && bundle exec rails s -b 0.0.0.0 -p 3000 > /tmp/rails.log 2>&1"

echo "==> Starting Ember CLI..."
docker exec -d -u discourse discourse_dev bash -c "cd /src && bin/ember-cli -p 4200 > /tmp/ember.log 2>&1"

echo "==> Waiting for Discourse to become ready..."
docker/scripts/wait-for-discourse.sh

echo "==> Bootstrap complete!"
echo "    Discourse is running at http://localhost:4200"
echo "    Admin: admin@opennotes.local / opennotes-dev-password"
