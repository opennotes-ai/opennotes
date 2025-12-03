"""add_server_default_to_requested_at

Revision ID: 59d60811c9a4
Revises: 0bbaec94d025
Create Date: 2025-10-29 16:58:34.003400

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "59d60811c9a4"
down_revision: str | Sequence[str] | None = "0bbaec94d025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add server default to requested_at column."""
    op.alter_column(
        "requests",
        "requested_at",
        server_default=sa.text("now()"),
        existing_type=sa.TIMESTAMP(),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Remove server default from requested_at column."""
    op.alter_column(
        "requests",
        "requested_at",
        server_default=None,
        existing_type=sa.TIMESTAMP(),
        existing_nullable=False,
    )
