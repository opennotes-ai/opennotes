"""Add tokens_valid_after field to users table

Revision ID: bb1298120943
Revises: 9369136951b7
Create Date: 2025-10-31 14:55:29.827826

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bb1298120943"
down_revision: str | Sequence[str] | None = "9369136951b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users", sa.Column("tokens_valid_after", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "tokens_valid_after")
