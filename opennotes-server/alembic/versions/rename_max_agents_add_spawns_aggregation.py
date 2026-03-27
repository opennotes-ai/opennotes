"""rename max_agents add max_total_spawns and rating_aggregation

Revision ID: a3f8b1c2d4e5
Revises: 1dceabf5c87e
Create Date: 2026-03-27
"""

import sqlalchemy as sa

from alembic import op

revision: str = "a3f8b1c2d4e5"
down_revision: str = "1dceabf5c87e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "simulation_orchestrators",
        "max_agents",
        new_column_name="max_active_agents",
    )
    op.add_column(
        "simulation_orchestrators",
        sa.Column("max_total_spawns", sa.Integer(), nullable=False, server_default="2000"),
    )

    op.drop_constraint(
        "ck_orchestrator_max_agents_positive",
        "simulation_orchestrators",
        type_="check",
    )
    op.create_check_constraint(
        "ck_orchestrator_max_active_agents_positive",
        "simulation_orchestrators",
        "max_active_agents > 0",
    )
    op.create_check_constraint(
        "ck_orchestrator_max_total_spawns_positive",
        "simulation_orchestrators",
        "max_total_spawns > 0",
    )

    op.alter_column(
        "simulation_run_configs",
        "max_agents",
        new_column_name="max_active_agents",
    )
    op.add_column(
        "simulation_run_configs",
        sa.Column("max_total_spawns", sa.Integer(), nullable=False, server_default="2000"),
    )

    op.add_column(
        "simulation_runs",
        sa.Column(
            "rating_aggregation",
            sa.String(30),
            nullable=False,
            server_default="aggregate_by_user_profile",
        ),
    )
    op.execute("UPDATE simulation_runs SET rating_aggregation = 'aggregate_by_agent_profile'")


def downgrade() -> None:
    op.drop_column("simulation_runs", "rating_aggregation")

    op.drop_column("simulation_run_configs", "max_total_spawns")
    op.alter_column(
        "simulation_run_configs",
        "max_active_agents",
        new_column_name="max_agents",
    )

    op.drop_constraint(
        "ck_orchestrator_max_total_spawns_positive",
        "simulation_orchestrators",
        type_="check",
    )
    op.drop_constraint(
        "ck_orchestrator_max_active_agents_positive",
        "simulation_orchestrators",
        type_="check",
    )
    op.create_check_constraint(
        "ck_orchestrator_max_agents_positive",
        "simulation_orchestrators",
        "max_agents > 0",
    )

    op.drop_column("simulation_orchestrators", "max_total_spawns")
    op.alter_column(
        "simulation_orchestrators",
        "max_active_agents",
        new_column_name="max_agents",
    )
