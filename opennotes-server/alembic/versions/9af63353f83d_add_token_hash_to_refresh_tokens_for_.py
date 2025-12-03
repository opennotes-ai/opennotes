"""Add token_hash to refresh_tokens for secure token storage

Revision ID: 9af63353f83d
Revises: b926b4628b74
Create Date: 2025-10-30 16:28:09.302631

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9af63353f83d"
down_revision: str | Sequence[str] | None = "b926b4628b74"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("refresh_tokens", sa.Column("token_hash", sa.String(length=255), nullable=True))
    op.create_index(
        op.f("ix_refresh_tokens_token_hash"), "refresh_tokens", ["token_hash"], unique=True
    )

    op.alter_column("refresh_tokens", "token", existing_type=sa.String(length=500), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("refresh_tokens", "token", existing_type=sa.String(length=500), nullable=False)

    op.drop_index(op.f("ix_refresh_tokens_token_hash"), table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "token_hash")
