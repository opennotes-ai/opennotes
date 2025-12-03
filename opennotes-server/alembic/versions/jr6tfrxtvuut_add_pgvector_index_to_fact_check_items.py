"""add pgvector index to fact check items

Revision ID: jr6tfrxtvuut
Revises: 4d775d88463a
Create Date: 2025-10-30 16:53:58.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "jr6tfrxtvuut"
down_revision: str | Sequence[str] | None = "4d775d88463a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add IVFFlat vector index to fact_check_items.embedding column.

    This index enables efficient similarity searches on embeddings using the
    IVFFlat (Inverted File with Flat compression) algorithm. The 'lists'
    parameter is set to 100, which is appropriate for datasets with < 1M rows.

    For larger datasets, consider increasing 'lists' to sqrt(row_count).
    """
    op.create_index(
        "idx_fact_check_items_embedding_ivfflat",
        "fact_check_items",
        ["embedding"],
        unique=False,
        postgresql_using="ivfflat",
        postgresql_with={"lists": 100},
    )


def downgrade() -> None:
    """Remove the IVFFlat vector index from fact_check_items.embedding."""
    op.drop_index(
        "idx_fact_check_items_embedding_ivfflat",
        table_name="fact_check_items",
        postgresql_using="ivfflat",
    )
