"""task_799_17_add_idx_requests_note_status

Revision ID: f8a9b1c2d3e4
Revises: c1e6dcebae91
Create Date: 2025-12-17 14:30:00.000000

Add composite index on requests.note_id + status for optimizing
the common query pattern of filtering requests by note_id and status.

Performance Impact:
- Optimizes queries filtering requests by both note_id and status
- Particularly useful for checking request status for specific notes

Related:
- Task-799.17: Code review finding - missing composite index
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f8a9b1c2d3e4"
down_revision: str | Sequence[str] | None = "c1e6dcebae91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add composite index on requests.note_id + status columns."""
    op.create_index(
        "idx_requests_note_status",
        "requests",
        ["note_id", "status"],
        unique=False,
        postgresql_using="btree",
    )


def downgrade() -> None:
    """Remove composite index on requests.note_id + status columns."""
    op.drop_index("idx_requests_note_status", table_name="requests")
