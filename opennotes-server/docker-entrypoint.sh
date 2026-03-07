#!/bin/bash
set -e

echo "=================================================="
echo "Open Notes Server - Startup"
echo "=================================================="

# Seed API keys for development if enabled
if [ "${SEED_DEV_API_KEYS}" = "true" ]; then
    echo "Seeding development API keys..."
    if ! python scripts/seed_api_keys.py; then
        echo "WARNING: Failed to seed API keys. Continuing anyway..."
    fi
fi

# Start the API server
echo "Starting API server..."
exec python -m src.main
