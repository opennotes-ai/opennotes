#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISCOURSE_DIR="$SCRIPT_DIR/../.discourse"

if [ ! -d "$DISCOURSE_DIR" ]; then
  echo "Error: Discourse not found at $DISCOURSE_DIR"
  echo "Nothing to shut down."
  exit 0
fi

cd "$DISCOURSE_DIR"

echo "==> Shutting down Discourse dev environment..."
d/shutdown_dev
echo "==> Discourse stopped."
