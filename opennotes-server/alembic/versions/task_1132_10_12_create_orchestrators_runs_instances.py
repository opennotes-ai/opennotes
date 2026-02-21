"""task-1132.10-12: create simulation_orchestrators, simulation_runs, sim_agent_instances tables

Also adds FK from sim_agent_memories.agent_instance_id to sim_agent_instances.id.

Revision ID: 8b4c5d6e7f8a
Revises: 7a3b4c5d6e7f
Create Date: 2026-02-21 12:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "8b4c5d6e7f8a"
down_revision: str | Sequence[str] | None = "7a3b4c5d6e7f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "simulation_orchestrators",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "community_server_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "turn_cadence_seconds",
            sa.Integer(),
            server_default="60",
            nullable=False,
        ),
        sa.Column(
            "max_agents",
            sa.Integer(),
            server_default="10",
            nullable=False,
        ),
        sa.Column(
            "removal_rate",
            sa.Float(),
            server_default="0.0",
            nullable=False,
        ),
        sa.Column(
            "max_turns_per_agent",
            sa.Integer(),
            server_default="100",
            nullable=False,
        ),
        sa.Column(
            "agent_profile_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "scoring_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["community_server_id"],
            ["community_servers.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.CheckConstraint(
            "turn_cadence_seconds > 0",
            name="ck_orchestrator_cadence_positive",
        ),
        sa.CheckConstraint(
            "max_agents > 0",
            name="ck_orchestrator_max_agents_positive",
        ),
        sa.CheckConstraint(
            "removal_rate >= 0 AND removal_rate <= 1",
            name="ck_orchestrator_removal_rate_range",
        ),
        sa.CheckConstraint(
            "max_turns_per_agent > 0",
            name="ck_orchestrator_max_turns_positive",
        ),
    )
    op.create_index(
        op.f("ix_simulation_orchestrators_id"),
        "simulation_orchestrators",
        ["id"],
    )
    op.create_index(
        op.f("ix_simulation_orchestrators_community_server_id"),
        "simulation_orchestrators",
        ["community_server_id"],
    )
    op.create_index(
        "idx_simulation_orchestrators_deleted_at",
        "simulation_orchestrators",
        ["deleted_at"],
    )
    op.create_index(
        "idx_simulation_orchestrators_is_active",
        "simulation_orchestrators",
        ["is_active"],
    )

    op.create_table(
        "simulation_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column(
            "orchestrator_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "community_server_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=True,
        ),
        sa.Column(
            "config_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["orchestrator_id"],
            ["simulation_orchestrators.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["community_server_id"],
            ["community_servers.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'paused', 'completed', 'cancelled', 'failed')",
            name="ck_simulation_runs_status",
        ),
    )
    op.create_index(op.f("ix_simulation_runs_id"), "simulation_runs", ["id"])
    op.create_index(
        op.f("ix_simulation_runs_orchestrator_id"),
        "simulation_runs",
        ["orchestrator_id"],
    )
    op.create_index(
        op.f("ix_simulation_runs_community_server_id"),
        "simulation_runs",
        ["community_server_id"],
    )
    op.create_index(
        op.f("ix_simulation_runs_status"),
        "simulation_runs",
        ["status"],
    )
    op.create_index(
        "idx_simulation_runs_deleted_at",
        "simulation_runs",
        ["deleted_at"],
    )
    op.create_index(
        "idx_simulation_runs_orchestrator_status",
        "simulation_runs",
        ["orchestrator_id", "status"],
    )

    op.create_table(
        "sim_agent_instances",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column(
            "simulation_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "agent_profile_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_profile_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.String(length=20),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "turn_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("last_turn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removal_reason", sa.String(length=100), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["simulation_run_id"],
            ["simulation_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_profile_id"],
            ["opennotes_sim_agents.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_profile_id"],
            ["user_profiles.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "state IN ('active', 'paused', 'completed', 'removed')",
            name="ck_sim_agent_instances_state",
        ),
        sa.CheckConstraint(
            "turn_count >= 0",
            name="ck_sim_agent_instances_turn_count_nonneg",
        ),
    )
    op.create_index(op.f("ix_sim_agent_instances_id"), "sim_agent_instances", ["id"])
    op.create_index(
        op.f("ix_sim_agent_instances_simulation_run_id"),
        "sim_agent_instances",
        ["simulation_run_id"],
    )
    op.create_index(
        op.f("ix_sim_agent_instances_agent_profile_id"),
        "sim_agent_instances",
        ["agent_profile_id"],
    )
    op.create_index(
        op.f("ix_sim_agent_instances_user_profile_id"),
        "sim_agent_instances",
        ["user_profile_id"],
    )
    op.create_index(
        op.f("ix_sim_agent_instances_state"),
        "sim_agent_instances",
        ["state"],
    )
    op.create_index(
        "idx_sim_agent_instances_deleted_at",
        "sim_agent_instances",
        ["deleted_at"],
    )
    op.create_index(
        "idx_sim_agent_instances_run_state",
        "sim_agent_instances",
        ["simulation_run_id", "state"],
    )

    op.create_foreign_key(
        "fk_sim_agent_memories_agent_instance_id",
        "sim_agent_memories",
        "sim_agent_instances",
        ["agent_instance_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_sim_agent_memories_agent_instance_id",
        "sim_agent_memories",
        type_="foreignkey",
    )

    op.drop_index(
        "idx_sim_agent_instances_run_state",
        table_name="sim_agent_instances",
    )
    op.drop_index(
        "idx_sim_agent_instances_deleted_at",
        table_name="sim_agent_instances",
    )
    op.drop_index(
        op.f("ix_sim_agent_instances_state"),
        table_name="sim_agent_instances",
    )
    op.drop_index(
        op.f("ix_sim_agent_instances_user_profile_id"),
        table_name="sim_agent_instances",
    )
    op.drop_index(
        op.f("ix_sim_agent_instances_agent_profile_id"),
        table_name="sim_agent_instances",
    )
    op.drop_index(
        op.f("ix_sim_agent_instances_simulation_run_id"),
        table_name="sim_agent_instances",
    )
    op.drop_index(
        op.f("ix_sim_agent_instances_id"),
        table_name="sim_agent_instances",
    )
    op.drop_table("sim_agent_instances")

    op.drop_index(
        "idx_simulation_runs_orchestrator_status",
        table_name="simulation_runs",
    )
    op.drop_index(
        "idx_simulation_runs_deleted_at",
        table_name="simulation_runs",
    )
    op.drop_index(
        op.f("ix_simulation_runs_status"),
        table_name="simulation_runs",
    )
    op.drop_index(
        op.f("ix_simulation_runs_community_server_id"),
        table_name="simulation_runs",
    )
    op.drop_index(
        op.f("ix_simulation_runs_orchestrator_id"),
        table_name="simulation_runs",
    )
    op.drop_index(
        op.f("ix_simulation_runs_id"),
        table_name="simulation_runs",
    )
    op.drop_table("simulation_runs")

    op.drop_index(
        "idx_simulation_orchestrators_is_active",
        table_name="simulation_orchestrators",
    )
    op.drop_index(
        "idx_simulation_orchestrators_deleted_at",
        table_name="simulation_orchestrators",
    )
    op.drop_index(
        op.f("ix_simulation_orchestrators_community_server_id"),
        table_name="simulation_orchestrators",
    )
    op.drop_index(
        op.f("ix_simulation_orchestrators_id"),
        table_name="simulation_orchestrators",
    )
    op.drop_table("simulation_orchestrators")
