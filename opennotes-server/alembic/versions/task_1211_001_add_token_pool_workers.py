"""task_1211_001_add_token_pool_workers

Add token_pool_workers table for per-worker dynamic capacity.

Revision ID: task_1211_001
Revises: wp04_001
Create Date: 2026-03-04

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "task_1211_001"
down_revision: str | None = "wp04_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "token_pool_workers",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column(
            "pool_name",
            sa.String(128),
            sa.ForeignKey("token_pools.pool_name"),
            nullable=False,
            index=True,
        ),
        sa.Column("worker_id", sa.String(256), nullable=False, index=True),
        sa.Column("capacity_contribution", sa.Integer(), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_heartbeat",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_token_pool_worker", "token_pool_workers", ["pool_name", "worker_id"]
    )


def downgrade() -> None:
    op.drop_table("token_pool_workers")
