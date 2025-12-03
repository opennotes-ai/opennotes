"""Add embedding_provider and embedding_model columns to fact_check_items

This migration adds columns to track which LLM provider and model were used to generate
embeddings. This enables proper version management, debugging, and migration when models change.

Revision ID: task_469_add_embedding_metadata
Revises: e27213685b1c
Create Date: 2025-11-07 10:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "task_469_add_embedding_metadata"
down_revision: str | Sequence[str] | None = "e27213685b1c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add embedding provider and model tracking columns."""
    # Add embedding_provider column
    op.add_column(
        "fact_check_items",
        sa.Column(
            "embedding_provider",
            sa.String(50),
            nullable=True,
            comment="LLM provider used for embedding generation (e.g., 'openai', 'anthropic')",
        ),
    )

    # Add embedding_model column
    op.add_column(
        "fact_check_items",
        sa.Column(
            "embedding_model",
            sa.String(100),
            nullable=True,
            comment="Model name used for embedding generation (e.g., 'text-embedding-3-small')",
        ),
    )

    # Backfill existing embeddings with current hardcoded values
    # All existing embeddings were generated with OpenAI's text-embedding-3-small model
    op.execute("""
        UPDATE fact_check_items
        SET embedding_provider = 'openai',
            embedding_model = 'text-embedding-3-small'
        WHERE embedding IS NOT NULL
          AND embedding_provider IS NULL
    """)

    # Add composite index for filtering by embedding version
    op.create_index(
        "idx_fact_check_items_embedding_version",
        "fact_check_items",
        ["embedding_provider", "embedding_model"],
    )


def downgrade() -> None:
    """Remove embedding provider and model columns."""
    # Drop the index
    op.drop_index("idx_fact_check_items_embedding_version", table_name="fact_check_items")

    # Drop the columns in reverse order
    op.drop_column("fact_check_items", "embedding_model")
    op.drop_column("fact_check_items", "embedding_provider")
