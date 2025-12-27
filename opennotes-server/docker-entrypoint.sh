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

# Determine the run mode
# RUN_MODE can be: server, worker, or both (default: server)
RUN_MODE="${RUN_MODE:-server}"

case "$RUN_MODE" in
    "server")
        echo "Starting API server only..."
        exec python -m src.main
        ;;
    "worker")
        echo "Starting taskiq worker only..."
        exec python -m taskiq worker src.tasks.broker:broker src.tasks.example
        ;;
    "both")
        echo "Starting API server and taskiq worker..."
        exec python scripts/run_with_worker.py
        ;;
    *)
        echo "ERROR: Unknown RUN_MODE: $RUN_MODE (expected: server, worker, or both)"
        exit 1
        ;;
esac
