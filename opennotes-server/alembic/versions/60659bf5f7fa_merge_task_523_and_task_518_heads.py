"""merge task-523 and task-518 heads

Revision ID: 60659bf5f7fa
Revises: a2a84a6e060a, d4d44d0f0621
Create Date: 2025-11-10 13:12:02.655529

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "60659bf5f7fa"
down_revision: str | Sequence[str] | None = ("a2a84a6e060a", "d4d44d0f0621")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
