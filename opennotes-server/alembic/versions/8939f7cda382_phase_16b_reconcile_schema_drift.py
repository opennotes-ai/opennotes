"""phase_16b_reconcile_schema_drift

Reconcile schema drift between model and DB state.
Handles cases where earlier migrations may not have fully applied
(CONCURRENTLY indexes, JSONB vs JSON type, nullable promotion).

Revision ID: 8939f7cda382
Revises: f7ee12c696d5
Create Date: 2026-04-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "8939f7cda382"
down_revision: str | Sequence[str] | None = "f7ee12c696d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Ensure principal_type is NOT NULL (migration 004 should have done this)
    op.alter_column("users", "principal_type", nullable=False, existing_type=sa.String())

    # Ensure platform_roles is JSONB not JSON
    op.alter_column(
        "users",
        "platform_roles",
        type_=JSONB(),
        existing_type=sa.JSON(),
        existing_nullable=False,
        existing_server_default=sa.text("'[]'::jsonb"),
    )

    # Ensure indexes exist (idempotent — check before creating)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("users")}

    if "idx_users_principal_type" not in existing_indexes:
        op.create_index("idx_users_principal_type", "users", ["principal_type"])

    if "idx_users_banned_at" not in existing_indexes:
        op.create_index(
            "idx_users_banned_at",
            "users",
            ["banned_at"],
            postgresql_where=sa.text("banned_at IS NOT NULL"),
        )

    if "idx_users_platform_roles_gin" not in existing_indexes:
        op.create_index(
            "idx_users_platform_roles_gin",
            "users",
            ["platform_roles"],
            postgresql_using="gin",
        )


def downgrade() -> None:
    pass
