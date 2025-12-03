#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "Starting Redis and NATS for integration tests..."
cd "${PROJECT_DIR}"

docker compose -f docker-compose.test.yml down -v 2>/dev/null || true

docker compose -f docker-compose.test.yml up -d

echo "Waiting for services to be healthy..."
timeout=60
elapsed=0

while [ $elapsed -lt $timeout ]; do
    if docker compose -f docker-compose.test.yml ps | grep -q "healthy"; then
        redis_healthy=$(docker compose -f docker-compose.test.yml ps redis-test | grep -c "healthy" || echo "0")
        nats_healthy=$(docker compose -f docker-compose.test.yml ps nats-test | grep -c "healthy" || echo "0")

        if [ "$redis_healthy" -eq 1 ] && [ "$nats_healthy" -eq 1 ]; then
            echo "All services are healthy!"
            break
        fi
    fi

    sleep 2
    elapsed=$((elapsed + 2))
    echo "Waiting... ($elapsed seconds)"
done

if [ $elapsed -ge $timeout ]; then
    echo "ERROR: Services did not become healthy in time"
    docker compose -f docker-compose.test.yml logs
    docker compose -f docker-compose.test.yml down -v
    exit 1
fi

export REDIS_URL="redis://localhost:6380/0"
export NATS_URL="nats://localhost:4223"
export DATABASE_URL="sqlite+aiosqlite:///:memory:"
export ENVIRONMENT="development"

echo "Running integration tests..."
if uv run pytest tests/test_integration_messaging.py -v "$@"; then
    echo "Integration tests passed!"
    TEST_EXIT_CODE=0
else
    echo "Integration tests failed!"
    TEST_EXIT_CODE=1
fi

echo "Cleaning up..."
docker compose -f docker-compose.test.yml down -v

exit $TEST_EXIT_CODE
