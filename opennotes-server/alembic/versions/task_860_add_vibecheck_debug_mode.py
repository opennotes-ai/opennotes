"""task_860_add_vibecheck_debug_mode

Add vibecheck_debug_mode column to community_servers table.
This enables verbose progress reporting during vibecheck operations.

Revision ID: 860a1b2c3d4e
Revises: 9a0353b49146
Create Date: 2025-12-22 14:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "860a1b2c3d4e"
down_revision: str | Sequence[str] | None = "9a0353b49146"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add vibecheck_debug_mode column to community_servers."""
    op.add_column(
        "community_servers",
        sa.Column(
            "vibecheck_debug_mode",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index(
        "idx_community_servers_vibecheck_debug_mode",
        "community_servers",
        ["vibecheck_debug_mode"],
        unique=False,
    )


def downgrade() -> None:
    """Remove vibecheck_debug_mode column from community_servers."""
    op.drop_index(
        "idx_community_servers_vibecheck_debug_mode",
        table_name="community_servers",
    )
    op.drop_column("community_servers", "vibecheck_debug_mode")
