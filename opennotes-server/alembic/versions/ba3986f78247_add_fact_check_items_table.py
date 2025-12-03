"""add_fact_check_items_table

Revision ID: ba3986f78247
Revises: f2a723620595
Create Date: 2025-10-29 14:05:53.813281

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ba3986f78247"
down_revision: str | Sequence[str] | None = "f2a723620595"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create fact_check_items table for storing fact-checking datasets with vector embeddings."""
    op.create_table(
        "fact_check_items",
        sa.Column("id", UUID(), nullable=False, default=sa.text("gen_random_uuid()")),
        sa.Column("dataset_name", sa.String(length=100), nullable=False),
        sa.Column("dataset_tags", ARRAY(sa.Text()), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("original_id", sa.String(length=255), nullable=True),
        sa.Column("published_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("rating", sa.String(length=50), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "array_length(dataset_tags, 1) > 0", name="check_dataset_tags_not_empty"
        ),
    )

    # Create indexes (except ivfflat which is created in a later migration)
    op.create_index("idx_fact_check_items_id", "fact_check_items", ["id"])
    op.create_index("idx_fact_check_items_dataset_name", "fact_check_items", ["dataset_name"])
    op.create_index(
        "idx_fact_check_items_dataset_tags",
        "fact_check_items",
        ["dataset_tags"],
        postgresql_using="gin",
    )
    op.create_index(
        "idx_fact_check_items_metadata", "fact_check_items", ["metadata"], postgresql_using="gin"
    )
    op.create_index("idx_fact_check_items_published_date", "fact_check_items", ["published_date"])
    op.create_index(
        "idx_fact_check_items_dataset_name_tags",
        "fact_check_items",
        ["dataset_name", "dataset_tags"],
    )


def downgrade() -> None:
    """Drop fact_check_items table."""
    op.drop_table("fact_check_items")
