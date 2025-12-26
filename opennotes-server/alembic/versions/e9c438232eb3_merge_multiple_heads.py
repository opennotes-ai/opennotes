"""merge multiple heads

Revision ID: e9c438232eb3
Revises: 87118a1b2c3d, 87141a1b2c3d
Create Date: 2025-12-26 11:58:46.855397

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "e9c438232eb3"
down_revision: str | Sequence[str] | None = ("87118a1b2c3d", "87141a1b2c3d")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
