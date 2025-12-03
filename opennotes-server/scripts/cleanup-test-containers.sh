#!/bin/bash

set -euo pipefail

echo "🧹 Cleaning up orphaned test containers..."

containers=$(docker ps -aq --filter "label=opennotes.test.session_id" --filter "status=running" || true)

if [ -z "$containers" ]; then
    echo "✓ No test containers found"
    exit 0
fi

echo "Found test containers:"
docker ps -a --filter "label=opennotes.test.session_id" --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.CreatedAt}}"
echo ""
echo "Stopping and removing containers..."
echo "$containers" | xargs -r docker stop -t 10 || true
echo "$containers" | xargs -r docker rm || true
echo "✓ Cleanup complete"
