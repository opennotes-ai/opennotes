"""merge task-1174 and main migration heads

Revision ID: f1f5cded5f4a
Revises: 0a36caa8cd3b, bc6e41fa5474
Create Date: 2026-02-25 15:11:07.569219

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "f1f5cded5f4a"
down_revision: str | Sequence[str] | None = ("0a36caa8cd3b", "bc6e41fa5474")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
