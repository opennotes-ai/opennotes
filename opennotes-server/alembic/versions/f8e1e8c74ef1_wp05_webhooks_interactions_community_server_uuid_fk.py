"""wp05_webhooks_interactions_community_server_uuid_fk

Revision ID: f8e1e8c74ef1
Revises: 254f9cdd210d
Create Date: 2026-01-27 18:35:15.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8e1e8c74ef1"
down_revision: str | Sequence[str] | None = "254f9cdd210d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert webhooks and interactions community_server_id from string to UUID FK."""
    # =============================================================
    # WEBHOOKS TABLE: String -> UUID FK (NOT NULL)
    # =============================================================

    # 1. Add new UUID column (nullable initially)
    op.add_column(
        "webhooks", sa.Column("community_server_id_new", UUID(as_uuid=True), nullable=True)
    )

    # 2. Backfill from community_servers via platform_community_server_id lookup
    op.execute("""
        UPDATE webhooks w
        SET community_server_id_new = cs.id
        FROM community_servers cs
        WHERE w.community_server_id = cs.platform_community_server_id
          AND w.community_server_id_new IS NULL
    """)

    # 3. Create placeholder community_servers for unmatched IDs
    op.execute("""
        INSERT INTO community_servers (id, platform, platform_community_server_id, name, is_active, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            'other',
            w.community_server_id,
            '[Unknown Community: ' || w.community_server_id || ']',
            false,
            NOW(),
            NOW()
        FROM webhooks w
        WHERE w.community_server_id_new IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM community_servers cs
            WHERE cs.platform_community_server_id = w.community_server_id
          )
        GROUP BY w.community_server_id
    """)

    # 4. Backfill newly created placeholders
    op.execute("""
        UPDATE webhooks w
        SET community_server_id_new = cs.id
        FROM community_servers cs
        WHERE w.community_server_id = cs.platform_community_server_id
          AND w.community_server_id_new IS NULL
    """)

    # 5. Make column non-nullable
    op.alter_column("webhooks", "community_server_id_new", nullable=False)

    # 6. Drop old column and index, rename new
    op.drop_index("ix_webhooks_community_server_id", table_name="webhooks")
    op.drop_column("webhooks", "community_server_id")
    op.alter_column("webhooks", "community_server_id_new", new_column_name="community_server_id")

    # 7. Add FK constraint and recreate index
    op.create_foreign_key(
        "fk_webhooks_community_server",
        "webhooks",
        "community_servers",
        ["community_server_id"],
        ["id"],
    )
    op.create_index("ix_webhooks_community_server_id", "webhooks", ["community_server_id"])

    # =============================================================
    # INTERACTIONS TABLE: String -> UUID FK (NULLABLE)
    # =============================================================

    # 1. Add new UUID column (nullable - will stay nullable)
    op.add_column(
        "interactions", sa.Column("community_server_id_new", UUID(as_uuid=True), nullable=True)
    )

    # 2. Backfill non-null values from community_servers
    op.execute("""
        UPDATE interactions i
        SET community_server_id_new = cs.id
        FROM community_servers cs
        WHERE i.community_server_id = cs.platform_community_server_id
          AND i.community_server_id IS NOT NULL
          AND i.community_server_id_new IS NULL
    """)

    # 3. Create placeholders for unmatched non-null values
    op.execute("""
        INSERT INTO community_servers (id, platform, platform_community_server_id, name, is_active, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            'other',
            i.community_server_id,
            '[Unknown Community: ' || i.community_server_id || ']',
            false,
            NOW(),
            NOW()
        FROM interactions i
        WHERE i.community_server_id IS NOT NULL
          AND i.community_server_id_new IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM community_servers cs
            WHERE cs.platform_community_server_id = i.community_server_id
          )
        GROUP BY i.community_server_id
    """)

    # 4. Backfill newly created placeholders
    op.execute("""
        UPDATE interactions i
        SET community_server_id_new = cs.id
        FROM community_servers cs
        WHERE i.community_server_id = cs.platform_community_server_id
          AND i.community_server_id IS NOT NULL
          AND i.community_server_id_new IS NULL
    """)

    # Note: DO NOT make non-nullable - NULLs stay NULL

    # 5. Drop old column and index, rename new
    op.drop_index("ix_interactions_community_server_id", table_name="interactions")
    op.drop_column("interactions", "community_server_id")
    op.alter_column(
        "interactions", "community_server_id_new", new_column_name="community_server_id"
    )

    # 6. Add FK constraint and recreate index (nullable FK is valid)
    op.create_foreign_key(
        "fk_interactions_community_server",
        "interactions",
        "community_servers",
        ["community_server_id"],
        ["id"],
    )
    op.create_index("ix_interactions_community_server_id", "interactions", ["community_server_id"])


def downgrade() -> None:
    """Revert webhooks and interactions community_server_id to string columns."""
    # =============================================================
    # INTERACTIONS TABLE: UUID -> String
    # =============================================================
    op.drop_constraint("fk_interactions_community_server", "interactions", type_="foreignkey")
    op.drop_index("ix_interactions_community_server_id", table_name="interactions")

    op.add_column(
        "interactions", sa.Column("community_server_id_old", sa.String(50), nullable=True)
    )

    op.execute("""
        UPDATE interactions i
        SET community_server_id_old = cs.platform_community_server_id
        FROM community_servers cs
        WHERE i.community_server_id = cs.id
    """)

    op.drop_column("interactions", "community_server_id")
    op.alter_column(
        "interactions", "community_server_id_old", new_column_name="community_server_id"
    )
    op.create_index("ix_interactions_community_server_id", "interactions", ["community_server_id"])

    # =============================================================
    # WEBHOOKS TABLE: UUID -> String
    # =============================================================
    op.drop_constraint("fk_webhooks_community_server", "webhooks", type_="foreignkey")
    op.drop_index("ix_webhooks_community_server_id", table_name="webhooks")

    op.add_column("webhooks", sa.Column("community_server_id_old", sa.String(50), nullable=True))

    op.execute("""
        UPDATE webhooks w
        SET community_server_id_old = cs.platform_community_server_id
        FROM community_servers cs
        WHERE w.community_server_id = cs.id
    """)

    op.alter_column("webhooks", "community_server_id_old", nullable=False)
    op.drop_column("webhooks", "community_server_id")
    op.alter_column("webhooks", "community_server_id_old", new_column_name="community_server_id")
    op.create_index("ix_webhooks_community_server_id", "webhooks", ["community_server_id"])
