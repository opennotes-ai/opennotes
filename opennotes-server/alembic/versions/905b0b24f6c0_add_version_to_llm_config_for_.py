"""add_version_to_llm_config_for_optimistic_locking

Revision ID: 905b0b24f6c0
Revises: 5bd462a30211
Create Date: 2025-10-30 18:12:55.243821

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "905b0b24f6c0"
down_revision: str | Sequence[str] | None = "5bd462a30211"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "community_server_llm_config",
        sa.Column("version", sa.BigInteger(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("community_server_llm_config", "version")
