"""task_1211_007_add_released_at_index_and_fk_cascade

Revision ID: 1db7b2f41382
Revises: 6d0da20fd824
Create Date: 2026-03-04 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "1db7b2f41382"
down_revision: str | Sequence[str] | None = "6d0da20fd824"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_token_holds_released_at", "token_holds", ["released_at"])

    op.drop_constraint("token_holds_pool_name_fkey", "token_holds", type_="foreignkey")
    op.create_foreign_key(
        "token_holds_pool_name_fkey",
        "token_holds",
        "token_pools",
        ["pool_name"],
        ["pool_name"],
        ondelete="CASCADE",
    )

    op.drop_constraint(
        "token_pool_workers_pool_name_fkey", "token_pool_workers", type_="foreignkey"
    )
    op.create_foreign_key(
        "token_pool_workers_pool_name_fkey",
        "token_pool_workers",
        "token_pools",
        ["pool_name"],
        ["pool_name"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "token_pool_workers_pool_name_fkey", "token_pool_workers", type_="foreignkey"
    )
    op.create_foreign_key(
        "token_pool_workers_pool_name_fkey",
        "token_pool_workers",
        "token_pools",
        ["pool_name"],
        ["pool_name"],
    )

    op.drop_constraint("token_holds_pool_name_fkey", "token_holds", type_="foreignkey")
    op.create_foreign_key(
        "token_holds_pool_name_fkey",
        "token_holds",
        "token_pools",
        ["pool_name"],
        ["pool_name"],
    )

    op.drop_index("ix_token_holds_released_at", "token_holds")
