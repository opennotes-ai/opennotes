"""add_provider_scope_to_user_identity

Revision ID: b58738457bfb
Revises: db483a298410
Create Date: 2026-03-27 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b58738457bfb"
down_revision: str | Sequence[str] | None = "db483a298410"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_identities",
        sa.Column("provider_scope", sa.String(length=255), server_default="*", nullable=False),
    )

    op.execute("UPDATE user_identities SET provider_scope = '*' WHERE provider_scope IS NULL")

    op.execute("COMMIT")

    op.drop_index(
        "idx_user_identities_provider_user",
        table_name="user_identities",
        postgresql_concurrently=True,
    )

    op.create_index(
        "idx_user_identities_provider_user",
        "user_identities",
        ["provider", "provider_scope", "provider_user_id"],
        unique=True,
        postgresql_concurrently=True,
    )


def downgrade() -> None:
    op.execute("COMMIT")

    op.drop_index(
        "idx_user_identities_provider_user",
        table_name="user_identities",
        postgresql_concurrently=True,
    )

    op.create_index(
        "idx_user_identities_provider_user",
        "user_identities",
        ["provider", "provider_user_id"],
        unique=True,
        postgresql_concurrently=True,
    )

    op.drop_column("user_identities", "provider_scope")
