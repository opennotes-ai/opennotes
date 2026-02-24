"""merge heads c83119a1f5aa and task1145001

Revision ID: 96eb91160c67
Revises: c83119a1f5aa, task1145001
Create Date: 2026-02-24 12:14:04.349348

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "96eb91160c67"
down_revision: str | Sequence[str] | None = ("c83119a1f5aa", "task1145001")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
