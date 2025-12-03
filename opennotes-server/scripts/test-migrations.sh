#!/usr/bin/env bash
#
# Migration Testing Script
# Tests database migrations in isolation with both SQLite and PostgreSQL
#
# Usage:
#   ./scripts/test-migrations.sh [--sqlite|--postgres|--all]
#

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

CONTAINER_NAME="opennotes-migration-test-$$"
POSTGRES_VERSION="${POSTGRES_VERSION:-16-alpine}"
POSTGRES_USER="${POSTGRES_USER:-migtest}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-migtest123}"
POSTGRES_DB="${POSTGRES_DB:-migtest}"

TEST_MODE="${1:-all}"

log_info() {
    echo -e "${BLUE}→ $1${NC}"
}

log_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

log_error() {
    echo -e "${RED}✗ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

find_random_port() {
    python3 -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()'
}

cleanup_postgres() {
    if [ -n "${POSTGRES_PORT:-}" ]; then
        log_info "Cleaning up PostgreSQL container..."
        docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
        docker rm "$CONTAINER_NAME" >/dev/null 2>&1 || true
        log_success "Cleanup complete"
    fi
}

verify_tables_and_indexes() {
    local db_url="$1"
    local db_type="$2"

    log_info "Verifying tables and indexes in $db_type..."

    local verify_script=$(cat <<'EOF'
import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def verify_schema(db_url):
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        if 'postgresql' in db_url:
            tables_query = """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """
            indexes_query = """
                SELECT tablename, indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                ORDER BY tablename, indexname
            """
        else:
            tables_query = """
                SELECT name as table_name
                FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """
            indexes_query = """
                SELECT tbl_name as tablename, name as indexname
                FROM sqlite_master
                WHERE type='index' AND tbl_name NOT LIKE 'sqlite_%'
                ORDER BY tbl_name, name
            """

        result = await conn.execute(text(tables_query))
        tables = [row[0] for row in result]

        result = await conn.execute(text(indexes_query))
        indexes = [(row[0], row[1]) for row in result]

        print(f"Tables found: {len(tables)}")
        for table in tables:
            print(f"  - {table}")

        print(f"\nIndexes found: {len(indexes)}")
        for table, index in indexes:
            print(f"  - {table}.{index}")

        expected_tables = [
            'alembic_version',
            'api_keys',
            'audit_logs',
            'interactions',
            'notes',
            'ratings',
            'refresh_tokens',
            'requests',
            'tasks',
            'users',
            'webhooks'
        ]

        missing = set(expected_tables) - set(tables)
        if missing:
            print(f"\n❌ Missing tables: {missing}")
            return False

        print(f"\n✓ All expected tables present")
        return True

    await engine.dispose()

if __name__ == "__main__":
    db_url = sys.argv[1]
    result = asyncio.run(verify_schema(db_url))
    sys.exit(0 if result else 1)
EOF
)

    echo "$verify_script" | uv run python - "$db_url"
    return $?
}

test_with_sample_data() {
    local db_url="$1"
    local db_type="$2"

    log_info "Testing migrations with sample data in $db_type..."

    local data_script=$(cat <<'EOF'
import asyncio
import sys
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def test_sample_data(db_url):
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        now_with_tz = datetime.now(timezone.utc)
        now_naive = datetime.now()

        await conn.execute(text("""
            INSERT INTO users (username, email, hashed_password, role, is_active, is_superuser, created_at, updated_at)
            VALUES ('testuser', 'test@example.com', 'hashed_password_123', 'user', true, false, :now, :now)
        """), {"now": now_with_tz})

        result = await conn.execute(text("SELECT id FROM users WHERE username = 'testuser'"))
        user_id = result.scalar()

        await conn.execute(text("""
            INSERT INTO notes (note_id, author_participant_id, created_at, tweet_id, summary, classification)
            VALUES (123456789, 'participant_123', :now, 987654321, 'Test note summary', 'NOT_MISLEADING')
        """), {"now": now_naive})

        result = await conn.execute(text("SELECT COUNT(*) FROM users"))
        user_count = result.scalar()

        result = await conn.execute(text("SELECT COUNT(*) FROM notes"))
        note_count = result.scalar()

        print(f"✓ Inserted {user_count} user(s)")
        print(f"✓ Inserted {note_count} note(s)")

        result = await conn.execute(text("SELECT username, email FROM users WHERE id = :id"), {"id": user_id})
        user = result.first()
        print(f"✓ Retrieved user: {user[0]} ({user[1]})")

        return True

    await engine.dispose()

if __name__ == "__main__":
    db_url = sys.argv[1]
    result = asyncio.run(test_sample_data(db_url))
    sys.exit(0 if result else 1)
EOF
)

    echo "$data_script" | uv run python - "$db_url"
    return $?
}

test_sqlite_migrations() {
    echo ""
    echo "========================================="
    echo "Testing SQLite Migrations"
    echo "========================================="
    echo ""

    SQLITE_DB="/tmp/test_migrations_$$.db"
    export DATABASE_URL="sqlite+aiosqlite:///${SQLITE_DB}"

    log_info "Using SQLite database: $SQLITE_DB"

    log_info "Step 1: Running 'alembic upgrade head' on clean database..."
    if uv run alembic upgrade head; then
        log_success "Migration upgrade successful"
    else
        log_error "Migration upgrade failed"
        rm -f "$SQLITE_DB"
        return 1
    fi

    log_info "Step 2: Checking current migration version..."
    uv run alembic current

    log_info "Step 3: Verifying all tables and indexes..."
    if verify_tables_and_indexes "$DATABASE_URL" "SQLite"; then
        log_success "Schema verification passed"
    else
        log_error "Schema verification failed"
        rm -f "$SQLITE_DB"
        return 1
    fi

    log_info "Step 4: Testing with sample data..."
    if test_with_sample_data "$DATABASE_URL" "SQLite"; then
        log_success "Sample data test passed"
    else
        log_error "Sample data test failed"
        rm -f "$SQLITE_DB"
        return 1
    fi

    log_info "Step 5: Testing rollback functionality (downgrade -1)..."
    if uv run alembic downgrade -1; then
        log_success "Rollback successful"
    else
        log_error "Rollback failed"
        rm -f "$SQLITE_DB"
        return 1
    fi

    log_info "Step 6: Checking version after rollback..."
    uv run alembic current

    log_info "Step 7: Re-applying migration (upgrade +1)..."
    if uv run alembic upgrade +1; then
        log_success "Re-upgrade successful"
    else
        log_error "Re-upgrade failed"
        rm -f "$SQLITE_DB"
        return 1
    fi

    log_info "Step 8: Testing full downgrade to base..."
    if uv run alembic downgrade base; then
        log_success "Full downgrade successful"
    else
        log_error "Full downgrade failed"
        rm -f "$SQLITE_DB"
        return 1
    fi

    log_info "Step 9: Re-applying all migrations..."
    if uv run alembic upgrade head; then
        log_success "Re-upgrade to head successful"
    else
        log_error "Re-upgrade to head failed"
        rm -f "$SQLITE_DB"
        return 1
    fi

    rm -f "$SQLITE_DB"
    log_success "SQLite migration tests completed successfully!"
    return 0
}

test_postgres_migrations() {
    echo ""
    echo "========================================="
    echo "Testing PostgreSQL Migrations"
    echo "========================================="
    echo ""

    trap cleanup_postgres EXIT INT TERM

    POSTGRES_PORT=$(find_random_port)
    log_info "Using port $POSTGRES_PORT for PostgreSQL"

    log_info "Starting PostgreSQL $POSTGRES_VERSION container..."
    docker run -d \
        --name "$CONTAINER_NAME" \
        -e POSTGRES_USER="$POSTGRES_USER" \
        -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
        -e POSTGRES_DB="$POSTGRES_DB" \
        -p "${POSTGRES_PORT}:5432" \
        postgres:"$POSTGRES_VERSION" \
        >/dev/null

    log_info "Waiting for PostgreSQL to be ready..."
    max_attempts=30
    attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if docker exec "$CONTAINER_NAME" pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1; then
            log_success "PostgreSQL is ready"
            break
        fi
        attempt=$((attempt + 1))
        if [ $attempt -eq $max_attempts ]; then
            log_error "PostgreSQL failed to start"
            return 1
        fi
        sleep 0.5
    done

    export DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT}/${POSTGRES_DB}"
    log_info "DATABASE_URL: $DATABASE_URL"

    log_info "Step 1: Running 'alembic upgrade head' on clean database..."
    if uv run alembic upgrade head; then
        log_success "Migration upgrade successful"
    else
        log_error "Migration upgrade failed"
        return 1
    fi

    log_info "Step 2: Checking current migration version..."
    uv run alembic current

    log_info "Step 3: Verifying all tables and indexes..."
    if verify_tables_and_indexes "$DATABASE_URL" "PostgreSQL"; then
        log_success "Schema verification passed"
    else
        log_error "Schema verification failed"
        return 1
    fi

    log_info "Step 4: Testing with sample data..."
    if test_with_sample_data "$DATABASE_URL" "PostgreSQL"; then
        log_success "Sample data test passed"
    else
        log_error "Sample data test failed"
        return 1
    fi

    log_info "Step 5: Testing rollback functionality (downgrade -1)..."
    if uv run alembic downgrade -1; then
        log_success "Rollback successful"
    else
        log_error "Rollback failed"
        return 1
    fi

    log_info "Step 6: Checking version after rollback..."
    uv run alembic current

    log_info "Step 7: Re-applying migration (upgrade +1)..."
    if uv run alembic upgrade +1; then
        log_success "Re-upgrade successful"
    else
        log_error "Re-upgrade failed"
        return 1
    fi

    log_info "Step 8: Testing full downgrade to base..."
    if uv run alembic downgrade base; then
        log_success "Full downgrade successful"
    else
        log_error "Full downgrade failed"
        return 1
    fi

    log_info "Step 9: Re-applying all migrations..."
    if uv run alembic upgrade head; then
        log_success "Re-upgrade to head successful"
    else
        log_error "Re-upgrade to head failed"
        return 1
    fi

    log_success "PostgreSQL migration tests completed successfully!"
    return 0
}

main() {
    echo "========================================="
    echo "Database Migration Testing Suite"
    echo "========================================="

    case "$TEST_MODE" in
        --sqlite)
            test_sqlite_migrations
            ;;
        --postgres)
            test_postgres_migrations
            ;;
        --all|*)
            test_sqlite_migrations
            SQLITE_RESULT=$?

            test_postgres_migrations
            POSTGRES_RESULT=$?

            echo ""
            echo "========================================="
            echo "Test Summary"
            echo "========================================="

            if [ $SQLITE_RESULT -eq 0 ]; then
                log_success "SQLite tests: PASSED"
            else
                log_error "SQLite tests: FAILED"
            fi

            if [ $POSTGRES_RESULT -eq 0 ]; then
                log_success "PostgreSQL tests: PASSED"
            else
                log_error "PostgreSQL tests: FAILED"
            fi

            if [ $SQLITE_RESULT -eq 0 ] && [ $POSTGRES_RESULT -eq 0 ]; then
                log_success "All migration tests passed!"
                return 0
            else
                log_error "Some migration tests failed"
                return 1
            fi
            ;;
    esac
}

main
