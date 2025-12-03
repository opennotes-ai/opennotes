"""Remove message_archive required check constraint

Revision ID: 175da5e91d70
Revises: acdfba44673a
Create Date: 2025-11-18 17:54:09.412414

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "175da5e91d70"
down_revision: str | Sequence[str] | None = "acdfba44673a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("ck_requests_message_archive_required", "requests", type_="check")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_check_constraint(
        "ck_requests_message_archive_required", "requests", "message_archive_id IS NOT NULL"
    )
