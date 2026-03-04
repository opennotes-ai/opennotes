"""merge task-1211 with main heads

Revision ID: 6d0da20fd824
Revises: task_1211_001, 02fa3f3de88f
Create Date: 2026-03-04 13:23:28.002780

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "6d0da20fd824"
down_revision: str | Sequence[str] | None = ("task_1211_001", "02fa3f3de88f")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
