"""Fix index naming for last_interaction_at column

Revision ID: fix_idx_naming_001
Revises: 63c4f9b236c4
Create Date: 2025-11-11 18:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fix_idx_naming_001"
down_revision: str | Sequence[str] | None = "63c4f9b236c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename index to match SQLAlchemy naming convention."""
    # Drop the incorrectly named index if it exists
    op.execute("DROP INDEX IF EXISTS idx_user_profiles_last_interaction_at")
    # Create with the correct naming convention only if it doesn't exist
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_profiles_last_interaction_at ON user_profiles (last_interaction_at)"
    )


def downgrade() -> None:
    """Revert index naming."""
    op.execute("DROP INDEX IF EXISTS ix_user_profiles_last_interaction_at")
    op.create_index(
        "idx_user_profiles_last_interaction_at",
        "user_profiles",
        ["last_interaction_at"],
        unique=False,
    )
