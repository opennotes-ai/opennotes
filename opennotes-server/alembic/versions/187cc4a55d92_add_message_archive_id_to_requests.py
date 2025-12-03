"""add_message_archive_id_to_requests

Revision ID: 187cc4a55d92
Revises: 0492756116a2
Create Date: 2025-10-29 12:09:40.470322

Adds message_archive_id column to requests table to link requests to archived messages.
This enables requests to reference the original Discord message from the message archive.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "187cc4a55d92"
down_revision: str | Sequence[str] | None = "0492756116a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add message_archive_id column to requests table."""
    op.add_column(
        "requests", sa.Column("message_archive_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_requests_message_archive_id",
        "requests",
        "message_archive",
        ["message_archive_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_requests_message_archive", "requests", ["message_archive_id"])


def downgrade() -> None:
    """Remove message_archive_id column from requests table."""
    op.drop_index("idx_requests_message_archive", table_name="requests")
    op.drop_constraint("fk_requests_message_archive_id", "requests", type_="foreignkey")
    op.drop_column("requests", "message_archive_id")
