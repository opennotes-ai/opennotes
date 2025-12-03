"""add_request_id_to_notes_and_original_message_content_to_requests

Revision ID: 8872d1ee5368
Revises: 83121d7ab7e5
Create Date: 2025-10-24 09:10:02.804198

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8872d1ee5368"
down_revision: str | Sequence[str] | None = "83121d7ab7e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add original_message_content to requests table
    op.add_column("requests", sa.Column("original_message_content", sa.Text(), nullable=True))

    # Add request_id to notes table with foreign key
    op.add_column("notes", sa.Column("request_id", sa.String(255), nullable=True))
    op.create_index("ix_notes_request_id", "notes", ["request_id"])
    op.create_foreign_key(
        "fk_notes_request_id", "notes", "requests", ["request_id"], ["request_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop foreign key and column from notes
    op.drop_constraint("fk_notes_request_id", "notes", type_="foreignkey")
    op.drop_index("ix_notes_request_id", "notes")
    op.drop_column("notes", "request_id")

    # Drop column from requests
    op.drop_column("requests", "original_message_content")
