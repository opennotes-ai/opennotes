#!/usr/bin/env python3
"""
Migration runner with PostgreSQL advisory lock support.

This script ensures that only one instance runs migrations at a time in
multi-instance deployments by using PostgreSQL advisory locks.
"""

import os
import subprocess
import sys

from sqlalchemy import create_engine, text

# Migration lock ID (hash of "opennotes_migrations")
MIGRATION_LOCK_ID = 1847334512


def acquire_lock_and_run_migrations():
    """Acquire advisory lock and run Alembic migrations."""
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set", file=sys.stderr)
        sys.exit(1)

    # Convert asyncpg URL to psycopg2 format for synchronous operations
    db_url_sync = database_url.replace("postgresql+asyncpg://", "postgresql://")

    print(f"Acquiring migration lock (ID: {MIGRATION_LOCK_ID})...")
    print("NOTE: If another instance is running migrations, this will wait...")

    # Create synchronous engine for lock acquisition
    engine = create_engine(db_url_sync, isolation_level="AUTOCOMMIT")

    try:
        with engine.connect() as conn:
            # Acquire advisory lock (blocks until available)
            conn.execute(text(f"SELECT pg_advisory_lock({MIGRATION_LOCK_ID})"))
            print("Migration lock acquired")

            # Run migrations while holding the lock
            print("Running database migrations...")
            result = subprocess.run(
                ["alembic", "upgrade", "head"], capture_output=True, text=True, check=False
            )

            # Print migration output
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)

            # Release advisory lock
            conn.execute(text(f"SELECT pg_advisory_unlock({MIGRATION_LOCK_ID})"))
            print("Migration lock released")

            if result.returncode != 0:
                print("ERROR: Migrations failed. Server will not start.", file=sys.stderr)
                sys.exit(1)

            print("Migrations completed successfully")

    except Exception as e:
        print(f"ERROR: Failed to run migrations: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    acquire_lock_and_run_migrations()
