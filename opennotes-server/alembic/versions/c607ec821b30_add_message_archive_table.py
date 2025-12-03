"""add_message_archive_table

Revision ID: c607ec821b30
Revises: 998489108130
Create Date: 2025-10-29 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c607ec821b30"
down_revision: str | Sequence[str] | None = "998489108130"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create message_archive table with indexes and constraints."""

    op.create_table(
        "message_archive",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("content_url", sa.String(length=2048), nullable=True),
        sa.Column("file_reference", sa.String(length=512), nullable=True),
        sa.Column("message_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("discord_message_id", sa.String(length=64), nullable=True),
        sa.Column("discord_channel_id", sa.String(length=64), nullable=True),
        sa.Column("discord_author_id", sa.String(length=64), nullable=True),
        sa.Column("discord_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "idx_message_archive_content_type", "message_archive", ["content_type"], unique=False
    )
    op.create_index(
        "idx_message_archive_created_at", "message_archive", [sa.desc("created_at")], unique=False
    )
    op.create_index(
        "idx_message_archive_discord_message",
        "message_archive",
        ["discord_message_id", "discord_channel_id"],
        unique=False,
    )
    op.create_index(
        "idx_message_archive_discord_message_id",
        "message_archive",
        ["discord_message_id"],
        unique=False,
    )
    op.create_index(
        "idx_message_archive_discord_channel_id",
        "message_archive",
        ["discord_channel_id"],
        unique=False,
    )
    op.create_index(
        "idx_message_archive_discord_author_id",
        "message_archive",
        ["discord_author_id"],
        unique=False,
    )
    op.create_index(
        "idx_message_archive_deleted_at",
        "message_archive",
        ["deleted_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    """Drop message_archive table and all indexes."""

    op.drop_index("idx_message_archive_deleted_at", table_name="message_archive")
    op.drop_index("idx_message_archive_discord_author_id", table_name="message_archive")
    op.drop_index("idx_message_archive_discord_channel_id", table_name="message_archive")
    op.drop_index("idx_message_archive_discord_message_id", table_name="message_archive")
    op.drop_index("idx_message_archive_discord_message", table_name="message_archive")
    op.drop_index("idx_message_archive_created_at", table_name="message_archive")
    op.drop_index("idx_message_archive_content_type", table_name="message_archive")
    op.drop_table("message_archive")
