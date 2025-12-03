"""add_monitored_channels_table

Revision ID: c8a4d6e9f1b2
Revises: ba3986f78247
Create Date: 2025-10-29 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8a4d6e9f1b2"
down_revision: str | Sequence[str] | None = "ba3986f78247"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create monitored_channels table for Discord channel monitoring configuration."""
    op.create_table(
        "monitored_channels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("community_server_id", sa.String(64), nullable=False),
        sa.Column("channel_id", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("similarity_threshold", sa.Float, nullable=False, server_default="0.85"),
        sa.Column("dataset_tags", ARRAY(sa.Text), nullable=False, server_default="{snopes}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("updated_by", sa.String(64), nullable=True),
        sa.UniqueConstraint("channel_id", name="uq_monitored_channels_channel_id"),
    )

    # Create indexes
    op.create_index("idx_monitored_channels_id", "monitored_channels", ["id"])
    op.create_index(
        "idx_monitored_channels_community_server_id", "monitored_channels", ["community_server_id"]
    )
    op.create_index("idx_monitored_channels_channel_id", "monitored_channels", ["channel_id"])
    op.create_index(
        "idx_monitored_channels_server_enabled",
        "monitored_channels",
        ["community_server_id", "enabled"],
    )
    op.create_index(
        "idx_monitored_channels_dataset_tags",
        "monitored_channels",
        ["dataset_tags"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Drop monitored_channels table."""
    op.drop_table("monitored_channels")
