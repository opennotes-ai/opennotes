"""Add data integrity constraints for legacy field migration

Revision ID: task229001
Revises: task180001
Create Date: 2025-11-01 12:05:00.000000

This migration addresses data integrity issues where models have both legacy
and new fields without constraints ensuring at least one is populated.

Constraints added:
1. Notes table: author_participant_id OR author_profile_id must be NOT NULL
2. Requests table: original_message_content OR message_archive_id must be NOT NULL

These constraints prevent:
- Orphaned notes if both author fields are NULL
- Missing content if both content fields are NULL
- Data inconsistency during the legacy field migration
"""

from alembic import op

revision = "task229001"
down_revision = "task180001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add CHECK constraint to notes table to ensure at least one author source exists
    op.create_check_constraint(
        "ck_notes_author_source",
        "notes",
        "author_participant_id IS NOT NULL OR author_profile_id IS NOT NULL",
    )

    # Add CHECK constraint to requests table to ensure at least one content source exists
    op.create_check_constraint(
        "ck_requests_content_source",
        "requests",
        "original_message_content IS NOT NULL OR message_archive_id IS NOT NULL",
    )


def downgrade() -> None:
    # Drop CHECK constraint from requests table
    op.drop_constraint("ck_requests_content_source", "requests", type_="check")

    # Drop CHECK constraint from notes table
    op.drop_constraint("ck_notes_author_source", "notes", type_="check")
