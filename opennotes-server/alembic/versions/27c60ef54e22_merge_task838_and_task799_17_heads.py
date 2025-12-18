"""merge_task838_and_task799_17_heads

Revision ID: 27c60ef54e22
Revises: 8d343d576c05, f8a9b1c2d3e4
Create Date: 2025-12-17 17:52:10.039519

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "27c60ef54e22"
down_revision: str | Sequence[str] | None = ("8d343d576c05", "f8a9b1c2d3e4")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
