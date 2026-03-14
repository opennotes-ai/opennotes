"""merge stuck-scan-fix and rls-policies heads

Revision ID: 8613f1914eb0
Revises: c2bb19d8c78c, d6267cf7c0d0
Create Date: 2026-03-14 16:58:24.200945

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "8613f1914eb0"
down_revision: str | Sequence[str] | None = ("c2bb19d8c78c", "d6267cf7c0d0")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
