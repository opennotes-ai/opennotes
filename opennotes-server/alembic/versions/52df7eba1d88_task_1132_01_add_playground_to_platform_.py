"""task-1132.01: add playground to platform check constraint

Revision ID: 52df7eba1d88
Revises: 771536fdfc75
Create Date: 2026-02-21 12:25:57.604618

"""

from collections.abc import Sequence

from alembic import op

revision: str = "52df7eba1d88"
down_revision: str | Sequence[str] | None = "771536fdfc75"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_community_servers_platform", "community_servers", type_="check")
    op.create_check_constraint(
        "ck_community_servers_platform",
        "community_servers",
        "platform IN ('discord', 'reddit', 'slack', 'matrix', 'discourse', 'playground', 'other')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_community_servers_platform", "community_servers", type_="check")
    op.create_check_constraint(
        "ck_community_servers_platform",
        "community_servers",
        "platform IN ('discord', 'reddit', 'slack', 'matrix', 'discourse', 'other')",
    )
