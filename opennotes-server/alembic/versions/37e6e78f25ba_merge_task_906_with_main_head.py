"""merge task-906 with main head

Revision ID: 37e6e78f25ba
Revises: 7549c4f824d8, 906a1b2c3d4e
Create Date: 2026-01-12 12:37:45.232210

"""

from collections.abc import Sequence

revision: str = "37e6e78f25ba"
down_revision: str | Sequence[str] | None = ("7549c4f824d8", "906a1b2c3d4e")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
