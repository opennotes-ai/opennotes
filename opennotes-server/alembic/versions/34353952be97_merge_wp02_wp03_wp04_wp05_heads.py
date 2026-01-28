"""merge_wp02_wp03_wp04_wp05_heads

Revision ID: 34353952be97
Revises: 436c8fc4c0c4, f8e1e8c74ef1, wp03_001, wp04_001
Create Date: 2026-01-28 11:34:15.751816

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "34353952be97"
down_revision: str | Sequence[str] | None = ("436c8fc4c0c4", "f8e1e8c74ef1", "wp03_001", "wp04_001")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
