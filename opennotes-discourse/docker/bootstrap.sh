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
  ln -sf ../../../ "$SYMLINK_TARGET"
else
  echo "==> Plugin symlink already exists"
fi

echo "==> Booting Discourse dev container..."
cd docker/.discourse && d/boot_dev --init
cd "$SCRIPT_DIR/.."

echo "==> Seeding admin user..."
cd docker/.discourse && d/rails runner "
  unless User.find_by(username: 'admin')
    user = User.create!(
      username: 'admin',
      email: 'admin@opennotes.local',
      password: 'opennotes-dev',
      active: true,
      approved: true,
      admin: true
    )
    user.activate
    user.grant_admin!
    puts 'Admin user created: admin@opennotes.local / opennotes-dev'
  else
    puts 'Admin user already exists'
  end
"
cd "$SCRIPT_DIR/.."

echo "==> Waiting for Discourse to become ready..."
docker/scripts/wait-for-discourse.sh

echo "==> Bootstrap complete!"
