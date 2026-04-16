"""merge_task1451_auth_redesign_with_task1401

Revision ID: 79604e21db28
Revises: 8939f7cda382, task1401_17
Create Date: 2026-04-16 12:53:10.226077

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "79604e21db28"
down_revision: str | Sequence[str] | None = ("8939f7cda382", "task1401_17")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
