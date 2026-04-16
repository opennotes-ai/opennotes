"""phase_15c: make api_keys.scopes NOT NULL with default []

Revision ID: 9214033f36bf
Revises: cfb0d3ca43cf
Create Date: 2026-04-15

Phase 1.5 — fixes TASK-1433.09 (NULL scopes = unrestricted access bug).

After phases 15a (backfill NULL scopes) and 15b (deactivate empty-array
keys), no active key should have NULL scopes. This migration enforces that
invariant at the DDL level by setting scopes NOT NULL with a server default
of '[]'.

The server default '[]' means any key created without an explicit scopes
value will have an empty array, which has_scope() now correctly treats as
no access (fail-closed).

Idempotency: ALTER COLUMN is idempotent — rerunning on an already-NOT-NULL
column is a no-op.

Ref: authorization-redesign-design.md Section 5, Phase 1.5
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9214033f36bf"
down_revision: str | Sequence[str] | None = "cfb0d3ca43cf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "api_keys",
        "scopes",
        server_default=sa.text("'[]'::jsonb"),
        nullable=False,
        existing_type=sa.JSON(),
    )


def downgrade() -> None:
    op.alter_column(
        "api_keys",
        "scopes",
        server_default=None,
        nullable=True,
        existing_type=sa.JSON(),
    )
