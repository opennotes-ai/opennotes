"""drop duplicate unique constraint on requests.request_id

Revision ID: 47b2c9e7dc9b
Revises: 454e533b87ec
Create Date: 2025-11-13 12:01:19.291947

"""

from collections.abc import Sequence

from alembic import op  # type: ignore[attr-defined]

# revision identifiers, used by Alembic.
revision: str = "47b2c9e7dc9b"
down_revision: str | Sequence[str] | None = "454e533b87ec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("notes_request_id_fkey", "notes", type_="foreignkey")
    op.drop_constraint(op.f("uq_requests_request_id"), "requests", type_="unique")
    op.create_foreign_key(
        None, "notes", "requests", ["request_id"], ["request_id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(None, "notes", type_="foreignkey")
    op.create_unique_constraint(
        op.f("uq_requests_request_id"),
        "requests",
        ["request_id"],
        postgresql_nulls_not_distinct=False,
    )
    op.create_foreign_key(
        "notes_request_id_fkey",
        "notes",
        "requests",
        ["request_id"],
        ["request_id"],
        ondelete="SET NULL",
    )
