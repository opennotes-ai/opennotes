"""merge task_900 and pg_cron heads

Revision ID: 8888a9c6b7c4
Revises: task_900_001, 94207a1b2c3d
Create Date: 2026-01-07 15:54:02.755952

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "8888a9c6b7c4"
down_revision: str | Sequence[str] | None = ("task_900_001", "94207a1b2c3d")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
