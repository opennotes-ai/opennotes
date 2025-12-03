"""task_444_rename_autopost_to_note_publisher

Revision ID: e7de94f6d297
Revises: 04fb5a0487df
Create Date: 2025-11-05 15:26:43.218486

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7de94f6d297"
down_revision: str | Sequence[str] | None = "04fb5a0487df"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename autopost tables and indexes to note_publisher for better semantic clarity.

    Renames:
    - auto_posts → note_publisher_posts
    - server_autopost_config → note_publisher_config
    - All associated indexes and constraints
    """

    # Rename auto_posts table to note_publisher_posts
    op.rename_table("auto_posts", "note_publisher_posts")

    # Rename all indexes on note_publisher_posts (formerly auto_posts)
    op.execute(
        "ALTER INDEX IF EXISTS ix_auto_posts_note_id RENAME TO ix_note_publisher_posts_note_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_auto_posts_original_message_id RENAME TO ix_note_publisher_posts_original_message_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_auto_posts_channel_id RENAME TO ix_note_publisher_posts_channel_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_auto_posts_posted_at RENAME TO ix_note_publisher_posts_posted_at"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_auto_posts_guild_id RENAME TO ix_note_publisher_posts_community_server_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_auto_posts_community_server_id RENAME TO ix_note_publisher_posts_community_server_id"
    )

    # Rename unique constraint on note_publisher_posts
    op.execute(
        "ALTER TABLE note_publisher_posts DROP CONSTRAINT IF EXISTS uq_auto_posts_original_message"
    )
    op.execute(
        "ALTER TABLE note_publisher_posts ADD CONSTRAINT uq_note_publisher_posts_original_message UNIQUE (original_message_id)"
    )

    # Rename server_autopost_config table to note_publisher_config
    op.rename_table("server_autopost_config", "note_publisher_config")

    # Rename all indexes on note_publisher_config (formerly server_autopost_config)
    op.execute(
        "ALTER INDEX IF EXISTS ix_server_autopost_config_guild_id RENAME TO ix_note_publisher_config_community_server_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_server_autopost_config_community_server_id RENAME TO ix_note_publisher_config_community_server_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_server_autopost_config_channel_id RENAME TO ix_note_publisher_config_channel_id"
    )

    # Rename unique constraint on note_publisher_config
    op.execute(
        "ALTER TABLE note_publisher_config DROP CONSTRAINT IF EXISTS uq_server_autopost_config_guild_channel"
    )
    op.execute(
        "ALTER TABLE note_publisher_config DROP CONSTRAINT IF EXISTS uq_server_autopost_config_community_server_channel"
    )
    op.execute(
        "ALTER TABLE note_publisher_config ADD CONSTRAINT uq_note_publisher_config_community_server_channel UNIQUE (community_server_id, channel_id)"
    )


def downgrade() -> None:
    """Revert note_publisher tables back to autopost naming.

    Reverts:
    - note_publisher_posts → auto_posts
    - note_publisher_config → server_autopost_config
    - All associated indexes and constraints
    """

    # Revert note_publisher_posts table to auto_posts
    op.rename_table("note_publisher_posts", "auto_posts")

    # Revert all indexes on auto_posts (formerly note_publisher_posts)
    op.execute(
        "ALTER INDEX IF EXISTS ix_note_publisher_posts_note_id RENAME TO ix_auto_posts_note_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_note_publisher_posts_original_message_id RENAME TO ix_auto_posts_original_message_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_note_publisher_posts_channel_id RENAME TO ix_auto_posts_channel_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_note_publisher_posts_posted_at RENAME TO ix_auto_posts_posted_at"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_note_publisher_posts_community_server_id RENAME TO ix_auto_posts_community_server_id"
    )

    # Revert unique constraint on auto_posts
    op.execute(
        "ALTER TABLE auto_posts DROP CONSTRAINT IF EXISTS uq_note_publisher_posts_original_message"
    )
    op.execute(
        "ALTER TABLE auto_posts ADD CONSTRAINT uq_auto_posts_original_message UNIQUE (original_message_id)"
    )

    # Revert note_publisher_config table to server_autopost_config
    op.rename_table("note_publisher_config", "server_autopost_config")

    # Revert all indexes on server_autopost_config (formerly note_publisher_config)
    op.execute(
        "ALTER INDEX IF EXISTS ix_note_publisher_config_community_server_id RENAME TO ix_server_autopost_config_community_server_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_note_publisher_config_channel_id RENAME TO ix_server_autopost_config_channel_id"
    )

    # Revert unique constraint on server_autopost_config
    op.execute(
        "ALTER TABLE server_autopost_config DROP CONSTRAINT IF EXISTS uq_note_publisher_config_community_server_channel"
    )
    op.execute(
        "ALTER TABLE server_autopost_config ADD CONSTRAINT uq_server_autopost_config_community_server_channel UNIQUE (community_server_id, channel_id)"
    )
