"""add_role_to_user_profiles

Revision ID: 2cfe6a0e7724
Revises: d3c8210eaa94
Create Date: 2025-10-30 12:24:19.583492

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2cfe6a0e7724"
down_revision: str | Sequence[str] | None = "d3c8210eaa94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add role column to user_profiles table."""
    op.add_column(
        "user_profiles",
        sa.Column("role", sa.String(length=50), nullable=False, server_default="user"),
    )
    op.create_index("idx_user_profiles_role", "user_profiles", ["role"])


def downgrade() -> None:
    """Remove role column from user_profiles table."""
    op.drop_index("idx_user_profiles_role", table_name="user_profiles")
    op.drop_column("user_profiles", "role")
