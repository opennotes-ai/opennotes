"""add_author_profile_id_to_notes

Revision ID: 0492756116a2
Revises: 94badc57d821
Create Date: 2025-10-29 12:07:55.731218

Adds author_profile_id column to notes table to link notes to user profiles.
This enables multiple authentication methods to link to the same authorship identity.
The legacy author_participant_id field is retained for data migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0492756116a2"
down_revision: str | Sequence[str] | None = "94badc57d821"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add author_profile_id column to notes table."""
    op.add_column(
        "notes", sa.Column("author_profile_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_notes_author_profile_id",
        "notes",
        "user_profiles",
        ["author_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_notes_author_profile_id", "notes", ["author_profile_id"])


def downgrade() -> None:
    """Remove author_profile_id column from notes table."""
    op.drop_index("idx_notes_author_profile_id", table_name="notes")
    op.drop_constraint("fk_notes_author_profile_id", "notes", type_="foreignkey")
    op.drop_column("notes", "author_profile_id")
