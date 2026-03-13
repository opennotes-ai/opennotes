"""enable RLS on all public tables

Revision ID: 458c433da8d8
Revises: 82909ed55243
Create Date: 2026-03-13 14:57:06.447902

"""

from collections.abc import Sequence

from alembic import op

revision: str = "458c433da8d8"
down_revision: str | Sequence[str] | None = "82909ed55243"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = [
    "api_keys",
    "audit_logs",
    "batch_jobs",
    "bulk_content_scan_logs",
    "chunk_embeddings",
    "community_config",
    "community_members",
    "community_server_llm_config",
    "community_servers",
    "fact_check_chunks",
    "fact_check_datasets",
    "fact_check_items",
    "fact_checked_item_candidates",
    "interactions",
    "llm_usage_log",
    "message_archive",
    "monitored_channels",
    "note_publisher_config",
    "note_publisher_posts",
    "notes",
    "opennotes_sim_agents",
    "previously_seen_chunks",
    "previously_seen_messages",
    "ratings",
    "refresh_tokens",
    "requests",
    "scoring_snapshots",
    "sim_agent_instances",
    "sim_agent_memories",
    "sim_agent_run_logs",
    "sim_channel_messages",
    "simulation_orchestrators",
    "simulation_run_configs",
    "simulation_runs",
    "token_holds",
    "token_pool_workers",
    "token_pools",
    "user_identities",
    "user_profiles",
    "users",
    "webhooks",
]


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
