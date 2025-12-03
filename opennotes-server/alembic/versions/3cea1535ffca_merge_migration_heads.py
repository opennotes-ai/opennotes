"""Merge migration heads

Revision ID: 3cea1535ffca
Revises: 905b0b24f6c0, 93b44bac0ce9
Create Date: 2025-10-30 18:15:26.623313

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "3cea1535ffca"
down_revision: str | Sequence[str] | None = ("905b0b24f6c0", "93b44bac0ce9")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
