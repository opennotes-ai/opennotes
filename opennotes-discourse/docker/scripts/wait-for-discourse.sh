#!/usr/bin/env bash
set -euo pipefail

URL="http://localhost:4200/srv/status"
TIMEOUT=120
INTERVAL=5
ELAPSED=0

echo "Waiting for Discourse at $URL (timeout: ${TIMEOUT}s)..."

while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
  if curl -sf "$URL" > /dev/null 2>&1; then
    echo ""
    echo "Discourse is ready!"
    exit 0
  fi
  printf "."
  sleep "$INTERVAL"
  ELAPSED=$((ELAPSED + INTERVAL))
done

echo ""
echo "Timed out after ${TIMEOUT}s waiting for Discourse"
exit 1
