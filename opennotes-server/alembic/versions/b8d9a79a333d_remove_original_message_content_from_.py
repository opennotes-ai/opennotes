"""Remove original_message_content column from requests table

Revision ID: b8d9a79a333d
Revises: 9fea737ffdc6
Create Date: 2025-11-04 08:33:42.060328

This migration removes the legacy original_message_content column from the requests table
and updates the check constraint to require message_archive_id instead of allowing either
original_message_content or message_archive_id.

The original_message_content column was kept temporarily for rollback safety during the
migration to store message archives. Now that the migration is complete and all requests
have message_archive_id populated, we can safely remove the legacy column.

Migration steps:
1. Drop the old check constraint that allowed either original_message_content OR message_archive_id
2. Remove the original_message_content column (no longer needed)
3. Create a new check constraint that requires message_archive_id IS NOT NULL
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8d9a79a333d"
down_revision: str | Sequence[str] | None = "9fea737ffdc6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Remove legacy original_message_content column and update the check constraint
    to require message_archive_id.
    """
    op.drop_constraint("ck_requests_content_source", "requests", type_="check")

    op.drop_column("requests", "original_message_content")

    op.create_check_constraint(
        "ck_requests_message_archive_required", "requests", "message_archive_id IS NOT NULL"
    )


def downgrade() -> None:
    """Downgrade schema.

    Restore the original_message_content column and revert the check constraint
    to allow either content source.
    """
    op.drop_constraint("ck_requests_message_archive_required", "requests", type_="check")

    op.add_column("requests", sa.Column("original_message_content", sa.Text(), nullable=True))

    op.create_check_constraint(
        "ck_requests_content_source",
        "requests",
        "original_message_content IS NOT NULL OR message_archive_id IS NOT NULL",
    )
