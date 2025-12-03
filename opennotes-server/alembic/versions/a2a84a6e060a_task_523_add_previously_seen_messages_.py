"""task-523: add previously_seen_messages table and threshold config

Revision ID: a2a84a6e060a
Revises: task_poi_001_convert_webhook_id_to_uuidv7
Create Date: 2025-11-10 21:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2a84a6e060a"
down_revision: str | None = "task_poi_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create previously_seen_messages table
    op.create_table(
        "previously_seen_messages",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), server_default=sa.text("uuidv7()"), nullable=False
        ),
        sa.Column("community_server_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "original_message_id",
            sa.String(length=64),
            nullable=False,
            comment="Platform-specific message ID",
        ),
        sa.Column(
            "published_note_id",
            sa.BigInteger(),
            nullable=False,
            comment="Note that was published for this message",
        ),
        sa.Column("embedding", Vector(dim=1536), nullable=True),
        sa.Column(
            "embedding_provider",
            sa.String(length=50),
            nullable=True,
            comment="LLM provider used for embedding generation (e.g., 'openai', 'anthropic')",
        ),
        sa.Column(
            "embedding_model",
            sa.String(length=100),
            nullable=True,
            comment="Model name used for embedding generation (e.g., 'text-embedding-3-small')",
        ),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["community_server_id"], ["community_servers.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["published_note_id"], ["notes.note_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for previously_seen_messages
    op.create_index(
        "idx_previously_seen_messages_community_server_id",
        "previously_seen_messages",
        ["community_server_id"],
        unique=False,
    )
    op.create_index(
        "idx_previously_seen_messages_original_message_id",
        "previously_seen_messages",
        ["original_message_id"],
        unique=False,
    )
    op.create_index(
        "idx_previously_seen_messages_published_note_id",
        "previously_seen_messages",
        ["published_note_id"],
        unique=False,
    )
    op.create_index(
        "idx_previously_seen_messages_metadata",
        "previously_seen_messages",
        ["metadata"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "idx_previously_seen_messages_embedding_version",
        "previously_seen_messages",
        ["embedding_provider", "embedding_model"],
        unique=False,
    )
    op.create_index(
        "idx_previously_seen_messages_embedding_ivfflat",
        "previously_seen_messages",
        ["embedding"],
        unique=False,
        postgresql_using="ivfflat",
        postgresql_with={"lists": 100},
    )
    op.create_index(
        "idx_previously_seen_messages_server_embedding",
        "previously_seen_messages",
        ["community_server_id", "embedding"],
        unique=False,
    )
    op.create_index(
        op.f("ix_previously_seen_messages_id"), "previously_seen_messages", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_previously_seen_messages_community_server_id"),
        "previously_seen_messages",
        ["community_server_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_previously_seen_messages_original_message_id"),
        "previously_seen_messages",
        ["original_message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_previously_seen_messages_published_note_id"),
        "previously_seen_messages",
        ["published_note_id"],
        unique=False,
    )

    # Add threshold columns to monitored_channels
    op.add_column(
        "monitored_channels",
        sa.Column(
            "previously_seen_autopublish_threshold",
            sa.Float(),
            nullable=True,
            comment="Override threshold for auto-publishing previously seen notes (NULL = use config default)",
        ),
    )
    op.add_column(
        "monitored_channels",
        sa.Column(
            "previously_seen_autorequest_threshold",
            sa.Float(),
            nullable=True,
            comment="Override threshold for auto-requesting notes on previously seen content (NULL = use config default)",
        ),
    )


def downgrade() -> None:
    # Remove threshold columns from monitored_channels
    op.drop_column("monitored_channels", "previously_seen_autorequest_threshold")
    op.drop_column("monitored_channels", "previously_seen_autopublish_threshold")

    # Drop indexes for previously_seen_messages
    op.drop_index(
        op.f("ix_previously_seen_messages_published_note_id"), table_name="previously_seen_messages"
    )
    op.drop_index(
        op.f("ix_previously_seen_messages_original_message_id"),
        table_name="previously_seen_messages",
    )
    op.drop_index(
        op.f("ix_previously_seen_messages_community_server_id"),
        table_name="previously_seen_messages",
    )
    op.drop_index(op.f("ix_previously_seen_messages_id"), table_name="previously_seen_messages")
    op.drop_index(
        "idx_previously_seen_messages_server_embedding", table_name="previously_seen_messages"
    )
    op.drop_index(
        "idx_previously_seen_messages_embedding_ivfflat",
        table_name="previously_seen_messages",
        postgresql_using="ivfflat",
    )
    op.drop_index(
        "idx_previously_seen_messages_embedding_version", table_name="previously_seen_messages"
    )
    op.drop_index(
        "idx_previously_seen_messages_metadata",
        table_name="previously_seen_messages",
        postgresql_using="gin",
    )
    op.drop_index(
        "idx_previously_seen_messages_published_note_id", table_name="previously_seen_messages"
    )
    op.drop_index(
        "idx_previously_seen_messages_original_message_id", table_name="previously_seen_messages"
    )
    op.drop_index(
        "idx_previously_seen_messages_community_server_id", table_name="previously_seen_messages"
    )

    # Drop previously_seen_messages table
    op.drop_table("previously_seen_messages")
