"""merge_task1422_03_and_task1428_01

Revision ID: f718d7324989
Revises: task1422_03, task1428_01
Create Date: 2026-04-15 12:52:22.710673

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "f718d7324989"
down_revision: str | Sequence[str] | None = ("task1422_03", "task1428_01")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
