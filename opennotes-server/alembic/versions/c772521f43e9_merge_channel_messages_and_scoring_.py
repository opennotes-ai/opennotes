"""merge channel messages and scoring snapshots

Revision ID: c772521f43e9
Revises: 0451fbf4ce30, 84eb220a346a
Create Date: 2026-03-10 15:49:58.018526

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "c772521f43e9"
down_revision: str | Sequence[str] | None = ("0451fbf4ce30", "84eb220a346a")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
