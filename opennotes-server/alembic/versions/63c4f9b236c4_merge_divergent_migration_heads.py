"""merge divergent migration heads

Revision ID: 63c4f9b236c4
Revises: 8510bfaa2741, task_521_add_last_interaction_at
Create Date: 2025-11-11 18:16:01.979090

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "63c4f9b236c4"
down_revision: str | Sequence[str] | None = (
    "8510bfaa2741",
    "task_521_add_last_interaction_at",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
