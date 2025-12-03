"""change_dataset_item_id_to_text_for_uuid

Revision ID: af5f4322c2d1
Revises: 9afd6edf6b4f
Create Date: 2025-11-06 10:01:55.649665

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "af5f4322c2d1"
down_revision: str | Sequence[str] | None = "9afd6edf6b4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Change dataset_item_id from integer to text to store UUID strings."""
    # Change column type from integer to text (VARCHAR)
    # Safe because column has no data (all values are NULL)
    op.alter_column(
        "requests",
        "dataset_item_id",
        type_=sa.String(length=36),  # UUID string length
        existing_type=sa.Integer(),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Revert dataset_item_id back to integer."""
    op.alter_column(
        "requests",
        "dataset_item_id",
        type_=sa.Integer(),
        existing_type=sa.String(length=36),
        existing_nullable=True,
    )
