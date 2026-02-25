"""add retry_count to sim_agent_instances

Revision ID: bc6e41fa5474
Revises: 96eb91160c67
Create Date: 2026-02-25

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "bc6e41fa5474"
down_revision: str | Sequence[str] | None = "96eb91160c67"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sim_agent_instances",
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("sim_agent_instances", "retry_count")
