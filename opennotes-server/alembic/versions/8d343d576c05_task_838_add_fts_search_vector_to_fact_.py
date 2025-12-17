"""task_838_add_fts_search_vector_to_fact_check_items

Revision ID: 8d343d576c05
Revises: e304e0f3f0e1
Create Date: 2025-12-16 18:05:38.072798

Adds PostgreSQL full-text search (FTS) support to the fact_check_items table:
- Adds search_vector column (TSVECTOR type) for FTS
- Creates GIN index for efficient FTS queries
- Creates trigger function for automatic tsvector updates
- Backfills existing rows with weighted tsvector values

Weight configuration:
- 'A' weight for title (highest relevance)
- 'B' weight for content (secondary relevance)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR

from alembic import op

revision: str = "8d343d576c05"
down_revision: str | Sequence[str] | None = "e304e0f3f0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add FTS search_vector column with trigger and GIN index to fact_check_items."""
    op.add_column(
        "fact_check_items",
        sa.Column("search_vector", TSVECTOR(), nullable=True),
    )

    op.create_index(
        "ix_fact_check_items_search_vector",
        "fact_check_items",
        ["search_vector"],
        postgresql_using="gin",
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fact_check_items_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.content, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER fact_check_items_search_vector_trigger
        BEFORE INSERT OR UPDATE ON fact_check_items
        FOR EACH ROW EXECUTE FUNCTION fact_check_items_search_vector_update();
        """
    )

    op.execute(
        """
        UPDATE fact_check_items SET search_vector =
            setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
            setweight(to_tsvector('english', COALESCE(content, '')), 'B');
        """
    )


def downgrade() -> None:
    """Remove FTS search_vector column, trigger, and function from fact_check_items."""
    op.execute("DROP TRIGGER IF EXISTS fact_check_items_search_vector_trigger ON fact_check_items;")

    op.execute("DROP FUNCTION IF EXISTS fact_check_items_search_vector_update();")

    op.drop_index("ix_fact_check_items_search_vector", table_name="fact_check_items")

    op.drop_column("fact_check_items", "search_vector")
