"""merge_heads_task_1368

Revision ID: db483a298410
Revises: 2a3373461956, a3f8b1c2d4e5
Create Date: 2026-03-27 18:26:56.359144

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "db483a298410"
down_revision: str | Sequence[str] | None = ("2a3373461956", "a3f8b1c2d4e5")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
