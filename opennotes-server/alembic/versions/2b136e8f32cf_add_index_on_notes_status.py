"""add_index_on_notes_status

Revision ID: 2b136e8f32cf
Revises: c8a4d6e9f1b2
Create Date: 2025-10-29 15:22:18.685142

Adds a standalone B-tree index on the notes.status column to optimize
queries that filter by status alone (e.g., /queue-notes command).

Performance Impact:
- Small datasets (<1000 notes): 10-50ms → 5-10ms
- Large datasets (>10,000 notes): 200-1000ms → 5-20ms

Related:
- Task-149: Performance diagnosis identified missing index
- Task-151: Implementation of index optimization
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2b136e8f32cf"
down_revision: str | Sequence[str] | None = "c8a4d6e9f1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add standalone index on notes.status column."""
    op.create_index("idx_notes_status", "notes", ["status"], unique=False, postgresql_using="btree")


def downgrade() -> None:
    """Remove standalone index on notes.status column."""
    op.drop_index("idx_notes_status", table_name="notes")
