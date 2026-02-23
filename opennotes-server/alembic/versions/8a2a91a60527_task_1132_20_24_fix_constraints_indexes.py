"""task-1132.20-24: fix constraints and indexes

Drop redundant PK indexes, add UNIQUE constraint on sim_agent_memories.agent_instance_id,
add CHECK constraint on memory_compaction_strategy, replace ix_ auto-indexes with named idx_ indexes.

Revision ID: 8a2a91a60527
Revises: 8b4c5d6e7f8a
Create Date: 2026-02-22 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8a2a91a60527"
down_revision: str | Sequence[str] | None = "8b4c5d6e7f8a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_opennotes_sim_agents_id")
    op.execute("DROP INDEX IF EXISTS ix_sim_agent_memories_id")
    op.execute("DROP INDEX IF EXISTS ix_simulation_orchestrators_id")
    op.execute("DROP INDEX IF EXISTS ix_simulation_runs_id")
    op.execute("DROP INDEX IF EXISTS ix_sim_agent_instances_id")

    op.execute("DROP INDEX IF EXISTS ix_simulation_runs_status")
    op.execute("DROP INDEX IF EXISTS idx_simulation_runs_status")
    op.execute(sa.text("CREATE INDEX idx_simulation_runs_status ON simulation_runs (status)"))

    op.execute("DROP INDEX IF EXISTS ix_sim_agent_instances_state")
    op.execute("DROP INDEX IF EXISTS idx_sim_agent_instances_state")
    op.execute(sa.text("CREATE INDEX idx_sim_agent_instances_state ON sim_agent_instances (state)"))

    op.execute("DROP INDEX IF EXISTS ix_sim_agent_memories_agent_instance_id")
    op.execute("DROP INDEX IF EXISTS idx_sim_agent_memories_agent_instance_id")
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX idx_sim_agent_memories_agent_instance_id "
            "ON sim_agent_memories (agent_instance_id)"
        )
    )

    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "ALTER TABLE opennotes_sim_agents ADD CONSTRAINT ck_sim_agents_memory_compaction_strategy "
            "CHECK (memory_compaction_strategy IN ('sliding_window', 'summarize_and_prune', 'semantic_dedup')); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE opennotes_sim_agents "
            "DROP CONSTRAINT IF EXISTS ck_sim_agents_memory_compaction_strategy"
        )
    )

    op.execute("DROP INDEX IF EXISTS idx_sim_agent_memories_agent_instance_id")
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_sim_agent_memories_agent_instance_id "
            "ON sim_agent_memories (agent_instance_id)"
        )
    )

    op.execute("DROP INDEX IF EXISTS idx_sim_agent_instances_state")
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_sim_agent_instances_state ON sim_agent_instances (state)"
        )
    )

    op.execute("DROP INDEX IF EXISTS idx_simulation_runs_status")
    op.execute(
        sa.text("CREATE INDEX IF NOT EXISTS ix_simulation_runs_status ON simulation_runs (status)")
    )

    op.execute(
        sa.text("CREATE INDEX IF NOT EXISTS ix_sim_agent_instances_id ON sim_agent_instances (id)")
    )
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_simulation_runs_id ON simulation_runs (id)"))
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_simulation_orchestrators_id "
            "ON simulation_orchestrators (id)"
        )
    )
    op.execute(
        sa.text("CREATE INDEX IF NOT EXISTS ix_sim_agent_memories_id ON sim_agent_memories (id)")
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_opennotes_sim_agents_id ON opennotes_sim_agents (id)"
        )
    )
