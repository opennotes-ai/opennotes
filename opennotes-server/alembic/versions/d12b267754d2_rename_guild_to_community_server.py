"""rename_guild_to_community_server

Revision ID: d12b267754d2
Revises: 8f3b900617c2
Create Date: 2025-10-29 11:33:40.843943

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d12b267754d2"
down_revision: str | Sequence[str] | None = "8f3b900617c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename guild references to community_server for platform-agnostic terminology.

    This migration renames columns and indexes to use 'community_server' instead of 'guild'
    to better represent the concept across different platforms (Discord servers, subreddits,
    Slack workspaces, etc.).
    """
    # Rename columns in webhooks table
    op.alter_column("webhooks", "guild_id", new_column_name="community_server_id")

    # Rename columns in interactions table
    op.alter_column("interactions", "guild_id", new_column_name="community_server_id")

    # Rename columns in community_config table
    op.alter_column("community_config", "community_id", new_column_name="community_server_id")

    # Rename indexes in community_config table (only if they exist)
    op.execute(
        "ALTER INDEX IF EXISTS ix_community_config_community_id RENAME TO ix_community_config_community_server_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_community_config_community_id_key RENAME TO ix_community_config_community_server_id_key"
    )

    # Rename columns in auto_posts table
    op.alter_column("auto_posts", "guild_id", new_column_name="community_server_id")

    # Rename columns in server_autopost_config table
    op.alter_column("server_autopost_config", "guild_id", new_column_name="community_server_id")

    # Rename constraint in server_autopost_config table
    op.execute(
        "ALTER TABLE server_autopost_config DROP CONSTRAINT IF EXISTS uq_server_autopost_config_guild_channel"
    )
    op.execute(
        "ALTER TABLE server_autopost_config ADD CONSTRAINT uq_server_autopost_config_community_server_channel UNIQUE (community_server_id, channel_id)"
    )


def downgrade() -> None:
    """Revert community_server references back to guild/community."""
    # Revert constraint in server_autopost_config table
    op.execute(
        "ALTER TABLE server_autopost_config DROP CONSTRAINT IF EXISTS uq_server_autopost_config_community_server_channel"
    )
    op.execute(
        "ALTER TABLE server_autopost_config ADD CONSTRAINT uq_server_autopost_config_guild_channel UNIQUE (guild_id, channel_id)"
    )

    # Revert columns in server_autopost_config table
    op.alter_column("server_autopost_config", "community_server_id", new_column_name="guild_id")

    # Revert columns in auto_posts table
    op.alter_column("auto_posts", "community_server_id", new_column_name="guild_id")

    # Revert indexes in community_config table
    op.execute(
        "ALTER INDEX ix_community_config_community_server_id_key RENAME TO ix_community_config_community_id_key"
    )
    op.execute(
        "ALTER INDEX ix_community_config_community_server_id RENAME TO ix_community_config_community_id"
    )

    # Revert columns in community_config table
    op.alter_column("community_config", "community_server_id", new_column_name="community_id")

    # Revert columns in interactions table
    op.alter_column("interactions", "community_server_id", new_column_name="guild_id")

    # Revert columns in webhooks table
    op.alter_column("webhooks", "community_server_id", new_column_name="guild_id")
