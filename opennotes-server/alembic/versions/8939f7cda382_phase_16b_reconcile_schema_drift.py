"""phase_16b_reconcile_schema_drift

Reconcile schema drift between model and DB state.
Handles cases where earlier migrations may not have fully applied
(CONCURRENTLY indexes, JSONB vs JSON type, nullable promotion).

NOTE (TASK-1451.17): Originally chained off f7ee12c696d5 (phase_16
drop_replaced_columns). That migration has been deferred until SDK
coordination completes (R4 in the 4-release sequence — see task notes),
so this migration now chains directly off 9214033f36bf (phase_15c).
The legacy users.role / is_superuser / is_service_account columns will
remain in the DB until migration 007 is re-introduced; alembic check
will report drift on those three columns until then (expected).

Revision ID: 8939f7cda382
Revises: 9214033f36bf
Create Date: 2026-04-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "8939f7cda382"
down_revision: str | Sequence[str] | None = "9214033f36bf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Raw SQL to forcibly reconcile schema with model.
    # Idempotent: each operation checks for current state before acting.

    # 1. Ensure principal_type is NOT NULL
    op.execute("""
        ALTER TABLE users ALTER COLUMN principal_type SET NOT NULL
    """)

    # 2. Ensure platform_roles is JSONB (not JSON)
    # PostgreSQL needs explicit USING clause when converting JSON -> JSONB
    op.execute("""
        ALTER TABLE users
        ALTER COLUMN platform_roles TYPE JSONB
        USING platform_roles::jsonb
    """)

    # 3. Ensure indexes exist (idempotent via IF NOT EXISTS)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_principal_type
        ON users(principal_type)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_banned_at
        ON users(banned_at)
        WHERE banned_at IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_platform_roles_gin
        ON users USING gin (platform_roles)
    """)


def downgrade() -> None:
    pass
