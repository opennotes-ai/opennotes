"""add_provider_scope_to_user_identity

Revision ID: b58738457bfb
Revises: db483a298410
Create Date: 2026-03-27 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

from alembic import op

revision: str = "b58738457bfb"
down_revision: str | Sequence[str] | None = "db483a298410"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "idx_user_identities_provider_user"
TABLE_NAME = "user_identities"
OLD_INDEX_COLUMNS = ["provider", "provider_user_id"]
NEW_INDEX_COLUMNS = ["provider", "provider_scope", "provider_user_id"]


def _get_index_columns(inspector, index_name: str) -> list[str] | None:
    for idx in inspector.get_indexes(TABLE_NAME):
        if idx["name"] == index_name:
            return list(idx.get("column_names", []))
    return None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    columns = [c["name"] for c in inspector.get_columns(TABLE_NAME)]
    existing_index_cols = _get_index_columns(inspector, INDEX_NAME)

    if "provider_scope" not in columns:
        op.add_column(
            TABLE_NAME,
            sa.Column("provider_scope", sa.String(length=255), server_default="*", nullable=False),
        )

    op.execute("UPDATE user_identities SET provider_scope = '*' WHERE provider_scope IS NULL")

    op.execute("COMMIT")

    if existing_index_cols == OLD_INDEX_COLUMNS:
        op.drop_index(
            INDEX_NAME,
            table_name=TABLE_NAME,
            postgresql_concurrently=True,
        )
        existing_index_cols = None

    if existing_index_cols is None:
        op.create_index(
            INDEX_NAME,
            TABLE_NAME,
            NEW_INDEX_COLUMNS,
            unique=True,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    columns = [c["name"] for c in inspector.get_columns(TABLE_NAME)]
    existing_index_cols = _get_index_columns(inspector, INDEX_NAME)

    op.execute("COMMIT")

    if existing_index_cols == NEW_INDEX_COLUMNS:
        op.drop_index(
            INDEX_NAME,
            table_name=TABLE_NAME,
            postgresql_concurrently=True,
        )
        existing_index_cols = None

    if existing_index_cols is None:
        op.create_index(
            INDEX_NAME,
            TABLE_NAME,
            OLD_INDEX_COLUMNS,
            unique=True,
            postgresql_concurrently=True,
        )

    if "provider_scope" in columns:
        op.drop_column(TABLE_NAME, "provider_scope")
