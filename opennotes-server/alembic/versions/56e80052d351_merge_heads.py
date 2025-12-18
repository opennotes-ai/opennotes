"""merge_heads

Revision ID: 56e80052d351
Revises: 8d343d576c05, f8a9b1c2d3e4
Create Date: 2025-12-17 17:41:31.675213

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "56e80052d351"
down_revision: str | Sequence[str] | None = ("8d343d576c05", "f8a9b1c2d3e4")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
