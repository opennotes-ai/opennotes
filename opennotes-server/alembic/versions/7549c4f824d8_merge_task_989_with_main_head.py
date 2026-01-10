"""merge task-989 with main head

Revision ID: 7549c4f824d8
Revises: cc3775845560, task989a1b2c3d
Create Date: 2026-01-09 15:15:33.491826

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "7549c4f824d8"
down_revision: str | Sequence[str] | None = ("cc3775845560", "task989a1b2c3d")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
