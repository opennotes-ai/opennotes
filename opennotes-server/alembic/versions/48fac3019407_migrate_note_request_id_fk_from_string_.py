"""migrate note request_id fk from string to uuid

Revision ID: 48fac3019407
Revises: 0dd89d1cf4df
Create Date: 2026-03-18 19:47:31.885839

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from alembic import op

revision: str = "48fac3019407"
down_revision: str | Sequence[str] | None = "0dd89d1cf4df"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_fk_on_column(table: str, column: str) -> None:
    connection = op.get_bind()
    result = connection.execute(
        text(
            "SELECT con.conname "
            "FROM pg_constraint con "
            "JOIN pg_attribute att ON att.attnum = ANY(con.conkey) "
            "AND att.attrelid = con.conrelid "
            f"WHERE con.conrelid = '{table}'::regclass "
            f"AND att.attname = '{column}' "
            "AND con.contype = 'f'"
        )
    )
    row = result.fetchone()
    if row:
        op.drop_constraint(row[0], table, type_="foreignkey")


def upgrade() -> None:
    _drop_fk_on_column("notes", "request_id")

    op.add_column("notes", sa.Column("request_uuid", PGUUID(as_uuid=True), nullable=True))

    op.execute(
        "UPDATE notes SET request_uuid = requests.id "
        "FROM requests WHERE notes.request_id = requests.request_id"
    )

    op.drop_index("ix_notes_request_id", table_name="notes")
    op.drop_column("notes", "request_id")

    op.alter_column("notes", "request_uuid", new_column_name="request_id")

    op.create_foreign_key(
        "notes_request_id_fkey",
        "notes",
        "requests",
        ["request_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_notes_request_id", "notes", ["request_id"])


def downgrade() -> None:
    _drop_fk_on_column("notes", "request_id")

    op.drop_index("ix_notes_request_id", table_name="notes")

    op.add_column("notes", sa.Column("request_id_str", sa.String(255), nullable=True))

    op.execute(
        "UPDATE notes SET request_id_str = requests.request_id "
        "FROM requests WHERE notes.request_id = requests.id"
    )

    op.drop_column("notes", "request_id")

    op.alter_column("notes", "request_id_str", new_column_name="request_id")

    op.create_foreign_key(
        "notes_request_id_fkey",
        "notes",
        "requests",
        ["request_id"],
        ["request_id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_notes_request_id", "notes", ["request_id"])
