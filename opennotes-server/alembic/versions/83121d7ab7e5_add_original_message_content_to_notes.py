"""add_original_message_content_to_notes

Revision ID: 83121d7ab7e5
Revises: b7e8f9a0b1c2
Create Date: 2025-10-23 17:08:59.561078

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "83121d7ab7e5"
down_revision: str | Sequence[str] | None = "b7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("notes", sa.Column("original_message_content", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("notes", "original_message_content")
