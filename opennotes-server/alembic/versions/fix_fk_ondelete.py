"""fix_fk_ondelete_constraints

Add missing ondelete settings to foreign key constraints.

Revision ID: fix_fk_ondelete
Revises: fix_workflow_id_unique
Create Date: 2026-01-29

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fix_fk_ondelete"
down_revision: str | Sequence[str] | None = "fix_workflow_id_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ondelete constraints to note_id FKs."""
    # Fix ratings.note_id FK - add CASCADE
    op.drop_constraint("ratings_note_id_fkey", "ratings", type_="foreignkey")
    op.create_foreign_key(
        "ratings_note_id_fkey",
        "ratings",
        "notes",
        ["note_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Fix requests.note_id FK - add SET NULL
    op.drop_constraint("requests_note_id_fkey", "requests", type_="foreignkey")
    op.create_foreign_key(
        "requests_note_id_fkey",
        "requests",
        "notes",
        ["note_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Remove ondelete constraints from note_id FKs."""
    # Restore ratings.note_id FK without ondelete
    op.drop_constraint("ratings_note_id_fkey", "ratings", type_="foreignkey")
    op.create_foreign_key(
        "ratings_note_id_fkey",
        "ratings",
        "notes",
        ["note_id"],
        ["id"],
    )

    # Restore requests.note_id FK without ondelete
    op.drop_constraint("requests_note_id_fkey", "requests", type_="foreignkey")
    op.create_foreign_key(
        "requests_note_id_fkey",
        "requests",
        "notes",
        ["note_id"],
        ["id"],
    )
