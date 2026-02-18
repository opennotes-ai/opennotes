"""merge task-1123 and task-1124 heads

Revision ID: 771536fdfc75
Revises: bf30f9abfc03, eadab3e9cb89
Create Date: 2026-02-17 17:09:54.961217

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "771536fdfc75"
down_revision: str | Sequence[str] | None = ("bf30f9abfc03", "eadab3e9cb89")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
