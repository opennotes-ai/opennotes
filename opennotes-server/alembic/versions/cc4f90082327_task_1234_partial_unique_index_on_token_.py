"""task-1234: partial unique index on token_holds

Revision ID: cc4f90082327
Revises: 1db7b2f41382
Create Date: 2026-03-06 13:42:43.054513

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "cc4f90082327"
down_revision: str | Sequence[str] | None = "1db7b2f41382"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_token_hold_pool_workflow", "token_holds", type_="unique")
    op.create_index(
        "uq_token_hold_pool_workflow",
        "token_holds",
        ["pool_name", "workflow_id"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_token_hold_pool_workflow",
        table_name="token_holds",
        postgresql_where=sa.text("released_at IS NULL"),
    )
    op.create_unique_constraint(
        "uq_token_hold_pool_workflow",
        "token_holds",
        ["pool_name", "workflow_id"],
    )
