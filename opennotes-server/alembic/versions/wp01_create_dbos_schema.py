"""wp01: create_dbos_schema

Create dedicated 'dbos' schema for DBOS workflow infrastructure.
DBOS will create its own system tables within this schema, isolating
workflow state from application tables in the 'public' schema.

Revision ID: wp01_create_dbos_schema
Revises: c1bd549e69ec
Create Date: 2026-01-28

"""

from collections.abc import Sequence

from alembic import op

revision: str = "wp01_create_dbos_schema"
down_revision: str | Sequence[str] | None = "c1bd549e69ec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS dbos")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS dbos CASCADE")
