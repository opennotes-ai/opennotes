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

# =============================================================================
# Middleware.io Host Agent (task-969)
# Start agent if MW_API_KEY is provided - collects host-level metrics
# =============================================================================
if [ -n "$MW_API_KEY" ] && [ -n "$MW_TARGET" ]; then
    if command -v mw-agent &> /dev/null; then
        echo "Starting Middleware.io host agent..."
        # Start agent in background with environment variables
        # Agent uses MW_API_KEY and MW_TARGET from environment
        mw-agent start &
        MW_AGENT_PID=$!
        echo "Middleware.io host agent started (PID: $MW_AGENT_PID)"
    else
        echo "WARNING: mw-agent not found, skipping host agent startup"
    fi
else
    echo "INFO: MW_API_KEY or MW_TARGET not set, skipping Middleware.io host agent"
fi

# Start the API server
# Note: Workers now run in a dedicated container/worker pool (see task-915)
echo "Starting API server..."
exec python -m src.main
