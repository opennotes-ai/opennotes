"""task-521: add last_interaction_at to user_profiles

Revision ID: task_521_add_last_interaction_at
Revises: task_508_add_cost_tracking
Create Date: 2025-11-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "task_521_add_last_interaction_at"
down_revision: str | Sequence[str] | None = "task_508_add_cost_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add last_interaction_at field to user_profiles."""
    op.add_column(
        "user_profiles",
        sa.Column(
            "last_interaction_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Add index for efficient querying
    op.create_index(
        "ix_user_profiles_last_interaction_at",
        "user_profiles",
        ["last_interaction_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove last_interaction_at field from user_profiles."""
    # Drop index first
    op.drop_index("ix_user_profiles_last_interaction_at", table_name="user_profiles")

    # Drop column
    op.drop_column("user_profiles", "last_interaction_at")
