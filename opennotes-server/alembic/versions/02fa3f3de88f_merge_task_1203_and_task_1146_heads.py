"""merge task-1203 and task-1146 heads

Revision ID: 02fa3f3de88f
Revises: a7c54bf2fe15, f804d09e16cc
Create Date: 2026-03-02 16:11:47.505674

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "02fa3f3de88f"
down_revision: str | Sequence[str] | None = ("a7c54bf2fe15", "f804d09e16cc")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
