"""task_863_01_remove_vibecheck_debug_mode_column

Remove vibecheck_debug_mode column from community_servers table.
This column is superseded by the community_config key-value store,
which is the correct location for this setting.

The Discord bot's /config opennotes set command writes to community_config,
so reading from community_servers.vibecheck_debug_mode was ineffective.

Revision ID: 86301a1b2c3d
Revises: 860a1b2c3d4e
Create Date: 2025-12-23 02:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "86301a1b2c3d"
down_revision: str | Sequence[str] | None = "860a1b2c3d4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove vibecheck_debug_mode column from community_servers."""
    op.drop_index(
        "ix_community_servers_vibecheck_debug_mode",
        table_name="community_servers",
    )
    op.drop_column("community_servers", "vibecheck_debug_mode")


def downgrade() -> None:
    """Re-add vibecheck_debug_mode column to community_servers."""
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
        "ix_community_servers_vibecheck_debug_mode",
        "community_servers",
        ["vibecheck_debug_mode"],
        unique=False,
    )
