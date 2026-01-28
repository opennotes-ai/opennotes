"""wp04_community_server_uuid_fk

Convert community_server_id from String to UUID FK for:
- monitored_channels
- note_publisher_posts
- note_publisher_config

Revision ID: wp04_001
Revises: 254f9cdd210d
Create Date: 2026-01-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "wp04_001"
down_revision: str | Sequence[str] | None = "254f9cdd210d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert community_server_id from String to UUID FK for all three tables."""

    # ========================================
    # STEP 1: Create placeholder community_servers for unmatched platform IDs
    # ========================================
    # Collect all unique platform IDs that don't exist in community_servers
    op.execute("""
        INSERT INTO community_servers (id, platform, platform_community_server_id, name, is_active, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            'unknown',
            platform_id,
            '[Unknown Community: ' || platform_id || ']',
            false,
            NOW(),
            NOW()
        FROM (
            SELECT DISTINCT community_server_id AS platform_id FROM monitored_channels
            UNION
            SELECT DISTINCT community_server_id AS platform_id FROM note_publisher_posts
            UNION
            SELECT DISTINCT community_server_id AS platform_id FROM note_publisher_config
        ) AS all_platform_ids
        WHERE NOT EXISTS (
            SELECT 1 FROM community_servers cs
            WHERE cs.platform_community_server_id = all_platform_ids.platform_id
        )
    """)

    # ========================================
    # STEP 2: monitored_channels
    # ========================================
    # Add new UUID column
    op.add_column(
        "monitored_channels",
        sa.Column("community_server_id_new", UUID(as_uuid=True), nullable=True),
    )

    # Backfill from community_servers via platform_community_server_id
    op.execute("""
        UPDATE monitored_channels mc
        SET community_server_id_new = cs.id
        FROM community_servers cs
        WHERE mc.community_server_id = cs.platform_community_server_id
    """)

    # Make column non-nullable
    op.alter_column("monitored_channels", "community_server_id_new", nullable=False)

    # Drop old column, rename new column
    op.drop_index("ix_monitored_channels_community_server_id", "monitored_channels")
    op.drop_index("idx_monitored_channels_server_enabled", "monitored_channels")
    op.drop_column("monitored_channels", "community_server_id")
    op.alter_column(
        "monitored_channels",
        "community_server_id_new",
        new_column_name="community_server_id",
    )

    # Add FK constraint and indexes
    op.create_foreign_key(
        "fk_monitored_channels_community_server",
        "monitored_channels",
        "community_servers",
        ["community_server_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_monitored_channels_community_server_id",
        "monitored_channels",
        ["community_server_id"],
    )
    op.create_index(
        "idx_monitored_channels_server_enabled",
        "monitored_channels",
        ["community_server_id", "enabled"],
    )

    # ========================================
    # STEP 3: note_publisher_posts
    # ========================================
    # Add new UUID column
    op.add_column(
        "note_publisher_posts",
        sa.Column("community_server_id_new", UUID(as_uuid=True), nullable=True),
    )

    # Backfill from community_servers via platform_community_server_id
    op.execute("""
        UPDATE note_publisher_posts npp
        SET community_server_id_new = cs.id
        FROM community_servers cs
        WHERE npp.community_server_id = cs.platform_community_server_id
    """)

    # Make column non-nullable
    op.alter_column("note_publisher_posts", "community_server_id_new", nullable=False)

    # Drop old column, rename new column
    op.drop_column("note_publisher_posts", "community_server_id")
    op.alter_column(
        "note_publisher_posts",
        "community_server_id_new",
        new_column_name="community_server_id",
    )

    # Add FK constraint and index
    op.create_foreign_key(
        "fk_note_publisher_posts_community_server",
        "note_publisher_posts",
        "community_servers",
        ["community_server_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_note_publisher_posts_community_server_id",
        "note_publisher_posts",
        ["community_server_id"],
    )

    # ========================================
    # STEP 4: note_publisher_config
    # ========================================
    # Add new UUID column
    op.add_column(
        "note_publisher_config",
        sa.Column("community_server_id_new", UUID(as_uuid=True), nullable=True),
    )

    # Backfill from community_servers via platform_community_server_id
    op.execute("""
        UPDATE note_publisher_config npc
        SET community_server_id_new = cs.id
        FROM community_servers cs
        WHERE npc.community_server_id = cs.platform_community_server_id
    """)

    # Make column non-nullable
    op.alter_column("note_publisher_config", "community_server_id_new", nullable=False)

    # Drop unique constraint before dropping column (it references community_server_id)
    op.drop_constraint(
        "uq_note_publisher_config_community_server_channel",
        "note_publisher_config",
        type_="unique",
    )

    # Drop old column, rename new column
    op.drop_column("note_publisher_config", "community_server_id")
    op.alter_column(
        "note_publisher_config",
        "community_server_id_new",
        new_column_name="community_server_id",
    )

    # Add FK constraint and index
    op.create_foreign_key(
        "fk_note_publisher_config_community_server",
        "note_publisher_config",
        "community_servers",
        ["community_server_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_note_publisher_config_community_server_id",
        "note_publisher_config",
        ["community_server_id"],
    )

    # Recreate unique constraint with new column
    op.create_unique_constraint(
        "uq_note_publisher_config_community_server_channel",
        "note_publisher_config",
        ["community_server_id", "channel_id"],
    )


def downgrade() -> None:
    """Reverse the migration: convert UUID FK back to String."""

    # ========================================
    # STEP 1: note_publisher_config
    # ========================================
    op.drop_constraint(
        "uq_note_publisher_config_community_server_channel",
        "note_publisher_config",
        type_="unique",
    )
    op.drop_constraint(
        "fk_note_publisher_config_community_server",
        "note_publisher_config",
        type_="foreignkey",
    )
    op.drop_index("ix_note_publisher_config_community_server_id", "note_publisher_config")

    op.add_column(
        "note_publisher_config",
        sa.Column("community_server_id_old", sa.String(64), nullable=True),
    )

    op.execute("""
        UPDATE note_publisher_config npc
        SET community_server_id_old = cs.platform_community_server_id
        FROM community_servers cs
        WHERE npc.community_server_id = cs.id
    """)

    op.alter_column("note_publisher_config", "community_server_id_old", nullable=False)
    op.drop_column("note_publisher_config", "community_server_id")
    op.alter_column(
        "note_publisher_config",
        "community_server_id_old",
        new_column_name="community_server_id",
    )

    op.create_unique_constraint(
        "uq_note_publisher_config_community_server_channel",
        "note_publisher_config",
        ["community_server_id", "channel_id"],
    )

    # ========================================
    # STEP 2: note_publisher_posts
    # ========================================
    op.drop_constraint(
        "fk_note_publisher_posts_community_server",
        "note_publisher_posts",
        type_="foreignkey",
    )
    op.drop_index("ix_note_publisher_posts_community_server_id", "note_publisher_posts")

    op.add_column(
        "note_publisher_posts",
        sa.Column("community_server_id_old", sa.String(64), nullable=True),
    )

    op.execute("""
        UPDATE note_publisher_posts npp
        SET community_server_id_old = cs.platform_community_server_id
        FROM community_servers cs
        WHERE npp.community_server_id = cs.id
    """)

    op.alter_column("note_publisher_posts", "community_server_id_old", nullable=False)
    op.drop_column("note_publisher_posts", "community_server_id")
    op.alter_column(
        "note_publisher_posts",
        "community_server_id_old",
        new_column_name="community_server_id",
    )

    # ========================================
    # STEP 3: monitored_channels
    # ========================================
    op.drop_constraint(
        "fk_monitored_channels_community_server",
        "monitored_channels",
        type_="foreignkey",
    )
    op.drop_index("ix_monitored_channels_community_server_id", "monitored_channels")
    op.drop_index("idx_monitored_channels_server_enabled", "monitored_channels")

    op.add_column(
        "monitored_channels",
        sa.Column("community_server_id_old", sa.String(64), nullable=True),
    )

    op.execute("""
        UPDATE monitored_channels mc
        SET community_server_id_old = cs.platform_community_server_id
        FROM community_servers cs
        WHERE mc.community_server_id = cs.id
    """)

    op.alter_column("monitored_channels", "community_server_id_old", nullable=False)
    op.drop_column("monitored_channels", "community_server_id")
    op.alter_column(
        "monitored_channels",
        "community_server_id_old",
        new_column_name="community_server_id",
    )

    op.create_index(
        "ix_monitored_channels_community_server_id",
        "monitored_channels",
        ["community_server_id"],
    )
    op.create_index(
        "idx_monitored_channels_server_enabled",
        "monitored_channels",
        ["community_server_id", "enabled"],
    )

    # Note: Placeholder community_servers created during upgrade are NOT deleted
    # to avoid data loss. They can be cleaned up manually if needed.
