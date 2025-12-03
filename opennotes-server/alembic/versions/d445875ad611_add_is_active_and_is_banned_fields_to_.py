"""Add is_active and is_banned fields to UserProfile

Revision ID: d445875ad611
Revises: 146b879b198d
Create Date: 2025-10-30 17:06:40.681265

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d445875ad611"
down_revision: str | Sequence[str] | None = "146b879b198d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "user_profiles", sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False)
    )
    op.add_column(
        "user_profiles", sa.Column("is_banned", sa.Boolean(), server_default="0", nullable=False)
    )
    op.add_column("user_profiles", sa.Column("banned_at", sa.DateTime(), nullable=True))
    op.add_column("user_profiles", sa.Column("banned_reason", sa.Text(), nullable=True))

    op.create_index("idx_user_profiles_is_active", "user_profiles", ["is_active"])
    op.create_index("idx_user_profiles_is_banned", "user_profiles", ["is_banned"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_user_profiles_is_banned", table_name="user_profiles")
    op.drop_index("idx_user_profiles_is_active", table_name="user_profiles")

    op.drop_column("user_profiles", "banned_reason")
    op.drop_column("user_profiles", "banned_at")
    op.drop_column("user_profiles", "is_banned")
    op.drop_column("user_profiles", "is_active")
