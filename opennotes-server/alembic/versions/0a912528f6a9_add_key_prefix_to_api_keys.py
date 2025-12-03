"""add_key_prefix_to_api_keys

Revision ID: 0a912528f6a9
Revises: 2cfe6a0e7724
Create Date: 2025-10-30 12:29:30.130675

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0a912528f6a9"
down_revision: str | Sequence[str] | None = "2cfe6a0e7724"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add key_prefix column to api_keys table for O(1) lookup."""
    op.add_column("api_keys", sa.Column("key_prefix", sa.String(length=16), nullable=True))
    op.create_index("idx_api_keys_key_prefix_active", "api_keys", ["key_prefix", "is_active"])


def downgrade() -> None:
    """Remove key_prefix column from api_keys table."""
    op.drop_index("idx_api_keys_key_prefix_active", table_name="api_keys")
    op.drop_column("api_keys", "key_prefix")
