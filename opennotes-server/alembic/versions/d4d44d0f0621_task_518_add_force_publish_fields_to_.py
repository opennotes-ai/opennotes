"""task-518: add force-publish fields to notes

Revision ID: d4d44d0f0621
Revises: b71da3475e5d
Create Date: 2025-11-08 18:10:21.985892

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4d44d0f0621"
down_revision: str | Sequence[str] | None = "b71da3475e5d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add force-publish fields to notes table."""
    op.add_column(
        "notes", sa.Column("force_published", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column("notes", sa.Column("force_published_by", UUID(as_uuid=True), nullable=True))
    op.add_column("notes", sa.Column("force_published_at", sa.DateTime(), nullable=True))

    op.create_foreign_key(
        "fk_notes_force_published_by",
        "notes",
        "user_profiles",
        ["force_published_by"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        op.f("ix_notes_force_published_by"), "notes", ["force_published_by"], unique=False
    )


def downgrade() -> None:
    """Remove force-publish fields from notes table."""
    op.drop_index(op.f("ix_notes_force_published_by"), table_name="notes")
    op.drop_constraint("fk_notes_force_published_by", "notes", type_="foreignkey")
    op.drop_column("notes", "force_published_at")
    op.drop_column("notes", "force_published_by")
    op.drop_column("notes", "force_published")
