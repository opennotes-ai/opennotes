"""Add comment to last_interaction_at column

Revision ID: fix_column_comment_001
Revises: fix_idx_naming_001
Create Date: 2025-11-11 18:35:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fix_column_comment_001"
down_revision: str | Sequence[str] | None = "fix_idx_naming_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add comment to last_interaction_at column."""
    op.alter_column(
        "user_profiles",
        "last_interaction_at",
        comment="Timestamp of the user's last interaction",
    )


def downgrade() -> None:
    """Remove comment from last_interaction_at column."""
    op.alter_column(
        "user_profiles",
        "last_interaction_at",
        comment=None,
    )
