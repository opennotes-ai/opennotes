"""add_compound_indexes_to_refresh_token

Revision ID: ac96bb16ac63
Revises: d05758dd2f3a
Create Date: 2025-11-01 11:19:05.352747

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ac96bb16ac63"
down_revision: str | Sequence[str] | None = "d05758dd2f3a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add compound indexes to refresh_tokens table for query optimization."""
    # Create compound index for token lookup with revoked status and expiration
    op.create_index(
        "idx_refresh_token_lookup",
        "refresh_tokens",
        ["token", "is_revoked", "expires_at"],
        unique=False,
    )

    # Create compound index for user-specific token queries with revoked status
    op.create_index(
        "idx_refresh_token_user_revoked",
        "refresh_tokens",
        ["user_id", "is_revoked"],
        unique=False,
    )


def downgrade() -> None:
    """Remove compound indexes from refresh_tokens table."""
    op.drop_index("idx_refresh_token_user_revoked", table_name="refresh_tokens")
    op.drop_index("idx_refresh_token_lookup", table_name="refresh_tokens")
