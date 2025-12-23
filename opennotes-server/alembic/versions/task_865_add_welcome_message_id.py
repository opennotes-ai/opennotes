"""task_865_add_welcome_message_id

Add welcome_message_id column to community_servers table.
Stores the Discord message ID of the welcome message posted in the bot channel.

Revision ID: 865a1b2c3d4e
Revises: 860a1b2c3d4e
Create Date: 2025-12-23 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "865a1b2c3d4e"
down_revision: str | Sequence[str] | None = "86301a1b2c3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add welcome_message_id column to community_servers."""
    op.add_column(
        "community_servers",
        sa.Column(
            "welcome_message_id",
            sa.String(30),
            nullable=True,
            comment="Discord message ID of the welcome message in bot channel",
        ),
    )


def downgrade() -> None:
    """Remove welcome_message_id column from community_servers."""
    op.drop_column("community_servers", "welcome_message_id")
