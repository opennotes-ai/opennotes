"""task-984: Add claim_hash column and update unique constraint

Adds claim_hash column to fact_checked_item_candidates table for content-based
deduplication. A single fact-check article can check multiple claims - e.g., one
Full Fact article checking '558k migrants' AND 'one million migrants' claims.

The claim_hash is an xxh3_64 hash of the claim text, providing a 16-character
hex string for efficient indexing and comparison.

Migration steps:
1. Add claim_hash column (nullable initially)
2. Backfill existing rows with hash of claim text from extracted_data
3. Make claim_hash NOT NULL
4. Drop old unique index on (source_url, dataset_name)
5. Create new unique index on (source_url, claim_hash, dataset_name)
6. Create index on claim_hash for lookups

Revision ID: 8669929ca521
Revises: 98102a1b2c3d
Create Date: 2026-01-08 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import xxhash

from alembic import op

revision: str = "8669929ca521"
down_revision: str | Sequence[str] | None = "98102a1b2c3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def compute_claim_hash(claim_text: str | None) -> str:
    """Compute xxh3_64 hash of claim text."""
    return xxhash.xxh3_64((claim_text or "").encode()).hexdigest()


def upgrade() -> None:
    # Step 1: Add claim_hash column as nullable
    op.add_column(
        "fact_checked_item_candidates",
        sa.Column(
            "claim_hash",
            sa.String(length=16),
            nullable=True,
            comment="xxh3_64 hash of claim text for multi-claim deduplication",
        ),
    )

    # Step 2: Backfill existing rows with hash computed from extracted_data->claim
    # Using a raw connection to fetch and update in batches
    conn = op.get_bind()

    # Fetch all existing rows that need backfill
    result = conn.execute(
        sa.text(
            """
            SELECT id, extracted_data->>'claim' as claim
            FROM fact_checked_item_candidates
            WHERE claim_hash IS NULL
            """
        )
    )
    rows = result.fetchall()

    # Update each row with computed hash
    for row in rows:
        claim_hash = compute_claim_hash(row.claim)
        conn.execute(
            sa.text(
                """
                UPDATE fact_checked_item_candidates
                SET claim_hash = :claim_hash
                WHERE id = :id
                """
            ),
            {"id": row.id, "claim_hash": claim_hash},
        )

    # Step 3: Make claim_hash NOT NULL
    op.alter_column(
        "fact_checked_item_candidates",
        "claim_hash",
        nullable=False,
    )

    # Step 4: Drop old unique index if exists (may not exist in all environments)
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_candidates_source_url_dataset"))

    # Step 5: Create new unique index with claim_hash
    op.create_index(
        "idx_candidates_source_url_claim_hash_dataset",
        "fact_checked_item_candidates",
        ["source_url", "claim_hash", "dataset_name"],
        unique=True,
    )

    # Step 6: Create index on claim_hash for lookups
    op.create_index(
        "idx_candidates_claim_hash",
        "fact_checked_item_candidates",
        ["claim_hash"],
    )


def downgrade() -> None:
    # Drop new indexes
    op.drop_index("idx_candidates_claim_hash", table_name="fact_checked_item_candidates")
    op.drop_index(
        "idx_candidates_source_url_claim_hash_dataset", table_name="fact_checked_item_candidates"
    )

    # Recreate old unique index
    op.create_index(
        "idx_candidates_source_url_dataset",
        "fact_checked_item_candidates",
        ["source_url", "dataset_name"],
        unique=True,
    )

    # Drop claim_hash column
    op.drop_column("fact_checked_item_candidates", "claim_hash")
