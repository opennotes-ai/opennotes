"""merge task_469 and task_490 heads

Revision ID: b10c6c2da1b8
Revises: task_469_add_embedding_metadata, task_490_phase_1c
Create Date: 2025-11-07 11:24:25.655242

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "b10c6c2da1b8"
down_revision: str | Sequence[str] | None = ("task_469_add_embedding_metadata", "task_490_phase_1c")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
