"""merge user profiles and message archive migrations

Revision ID: 8f3b900617c2
Revises: c607ec821b30, 1fc2d611a071
Create Date: 2025-10-29 10:05:41.409421

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "8f3b900617c2"
down_revision: str | Sequence[str] | None = ("c607ec821b30", "1fc2d611a071")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
