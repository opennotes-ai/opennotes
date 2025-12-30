#!/bin/bash
set -e

echo "=================================================="
echo "Open Notes Server - Startup"
echo "=================================================="

# Run migrations (unless skipped)
if [ "${SKIP_MIGRATIONS}" = "true" ]; then
    echo "INFO: SKIP_MIGRATIONS is set to true, skipping database migrations"
else
    # Run migrations with PostgreSQL advisory lock
    # This ensures only one instance runs migrations at a time
    python scripts/run_migrations_with_lock.py

    if [ $? -ne 0 ]; then
        echo "ERROR: Migration process failed. Server will not start."
        exit 1
    fi
fi

# Seed API keys for development if enabled
if [ "${SEED_DEV_API_KEYS}" = "true" ]; then
    echo "Seeding development API keys..."
    python scripts/seed_api_keys.py
    if [ $? -ne 0 ]; then
        echo "WARNING: Failed to seed API keys. Continuing anyway..."
    fi
fi

# Start the API server
# Note: Workers now run in a dedicated container/worker pool (see task-915)
echo "Starting API server..."
exec python -m src.main
