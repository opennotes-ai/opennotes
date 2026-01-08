"""task-981.02: Add fact_checked_item_candidates table

Create fact_checked_item_candidates table for storing candidate fact-check
items awaiting processing or review before promotion to fact_check_items.

Candidates go through a pipeline:
1. pending - Initial state after import/crawl
2. scraping - Content scraping in progress
3. scraped - Content successfully scraped
4. scrape_failed - Content scraping failed
5. promoted - Successfully promoted to fact_check_items

Revision ID: 98102a1b2c3d
Revises: 8888a9c6b7c4
Create Date: 2026-01-07 19:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "98102a1b2c3d"
down_revision: str | Sequence[str] | None = "8888a9c6b7c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fact_checked_item_candidates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("rating", sa.String(length=100), nullable=True),
        sa.Column(
            "predicted_ratings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("published_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dataset_name", sa.String(length=100), nullable=False),
        sa.Column(
            "dataset_tags",
            postgresql.ARRAY(sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("original_id", sa.String(length=255), nullable=True),
        sa.Column(
            "extracted_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index(
        op.f("ix_fact_checked_item_candidates_id"), "fact_checked_item_candidates", ["id"]
    )
    op.create_index(
        "idx_candidates_source_url_dataset",
        "fact_checked_item_candidates",
        ["source_url", "dataset_name"],
        unique=True,
    )
    op.create_index("idx_candidates_status", "fact_checked_item_candidates", ["status"])
    op.create_index(
        "idx_candidates_dataset_tags",
        "fact_checked_item_candidates",
        ["dataset_tags"],
        postgresql_using="gin",
    )
    op.create_index(
        "idx_candidates_extracted_data",
        "fact_checked_item_candidates",
        ["extracted_data"],
        postgresql_using="gin",
    )
    op.create_index(
        "idx_candidates_published_date", "fact_checked_item_candidates", ["published_date"]
    )
    op.create_index("idx_candidates_original_id", "fact_checked_item_candidates", ["original_id"])
    op.create_index("idx_candidates_dataset_name", "fact_checked_item_candidates", ["dataset_name"])
    op.create_index("idx_candidates_source_url", "fact_checked_item_candidates", ["source_url"])


def downgrade() -> None:
    op.drop_index("idx_candidates_source_url", table_name="fact_checked_item_candidates")
    op.drop_index("idx_candidates_dataset_name", table_name="fact_checked_item_candidates")
    op.drop_index("idx_candidates_original_id", table_name="fact_checked_item_candidates")
    op.drop_index("idx_candidates_published_date", table_name="fact_checked_item_candidates")
    op.drop_index("idx_candidates_extracted_data", table_name="fact_checked_item_candidates")
    op.drop_index("idx_candidates_dataset_tags", table_name="fact_checked_item_candidates")
    op.drop_index("idx_candidates_status", table_name="fact_checked_item_candidates")
    op.drop_index("idx_candidates_source_url_dataset", table_name="fact_checked_item_candidates")
    op.drop_index(
        op.f("ix_fact_checked_item_candidates_id"), table_name="fact_checked_item_candidates"
    )
    op.drop_table("fact_checked_item_candidates")
