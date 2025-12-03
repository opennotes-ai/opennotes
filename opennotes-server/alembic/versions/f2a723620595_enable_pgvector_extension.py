"""enable_pgvector_extension

Revision ID: f2a723620595
Revises: afb0dd43182b
Create Date: 2025-10-29 14:08:25.837169

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a723620595"
down_revision: str | Sequence[str] | None = "afb0dd43182b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enable pgvector extension for vector similarity search."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Disable pgvector extension."""
    op.execute("DROP EXTENSION IF EXISTS vector CASCADE")
