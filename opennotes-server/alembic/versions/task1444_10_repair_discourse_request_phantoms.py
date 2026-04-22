"""Repair Discourse request rows attached to phantom Discord community servers.

Revision ID: task1444_10
Revises: task1450_21
Create Date: 2026-04-21

TASK-1444.10 - POST /requests previously resolved every
``community_server_id`` under ``platform='discord'``. After the Discourse
plugin began sending its platform slug, that path could auto-create a
``platform='discord'`` row whose ``platform_community_server_id`` matched an
existing registered Discourse slug. Requests created during that window belong
to the registered Discourse row instead.

Idempotency: the migration computes phantom/canonical pairs from current table
state, updates only rows still pointing at the phantom id, and deletes only
phantom rows left without references. Re-running after cleanup is a no-op.
Downgrade is intentionally a no-op because recreating known-bad phantom tenant
rows would reintroduce incorrect routing.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "task1444_10"
down_revision: str | Sequence[str] | None = "task1450_21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PHANTOM_MATCHES_SQL = """
    SELECT
        phantom.id AS phantom_id,
        canonical.id AS canonical_id
      FROM community_servers AS phantom
      JOIN community_servers AS canonical
        ON canonical.platform = 'discourse'
       AND canonical.platform_community_server_id = phantom.platform_community_server_id
     WHERE phantom.platform = 'discord'
       AND phantom.id <> canonical.id
"""


def upgrade() -> None:
    op.execute(
        f"""
        WITH phantom_matches AS (
            {PHANTOM_MATCHES_SQL}
        )
        UPDATE requests AS request_row
           SET community_server_id = phantom_matches.canonical_id
          FROM phantom_matches
         WHERE request_row.community_server_id = phantom_matches.phantom_id
        """
    )

    op.execute(
        f"""
        WITH phantom_matches AS (
            {PHANTOM_MATCHES_SQL}
        )
        DELETE FROM community_servers AS community_server
         USING phantom_matches
         WHERE community_server.id = phantom_matches.phantom_id
           AND NOT EXISTS (
               SELECT 1 FROM requests
                WHERE requests.community_server_id = community_server.id
           )
           AND NOT EXISTS (
               SELECT 1 FROM notes
                WHERE notes.community_server_id = community_server.id
           )
           AND NOT EXISTS (
               SELECT 1 FROM moderation_actions
                WHERE moderation_actions.community_server_id = community_server.id
           )
           AND NOT EXISTS (
               SELECT 1 FROM monitored_channels
                WHERE monitored_channels.community_server_id = community_server.id
           )
           AND NOT EXISTS (
               SELECT 1 FROM community_config
                WHERE community_config.community_server_id = community_server.id
           )
           AND NOT EXISTS (
               SELECT 1 FROM community_server_llm_config
                WHERE community_server_llm_config.community_server_id = community_server.id
           )
           AND NOT EXISTS (
               SELECT 1 FROM community_members
                WHERE community_members.community_id = community_server.id
           )
           AND NOT EXISTS (
               SELECT 1 FROM webhooks
                WHERE webhooks.community_server_id = community_server.id
           )
           AND NOT EXISTS (
               SELECT 1 FROM interactions
                WHERE interactions.community_server_id = community_server.id
           )
           AND NOT EXISTS (
               SELECT 1 FROM bulk_content_scan_logs
                WHERE bulk_content_scan_logs.community_server_id = community_server.id
           )
           AND NOT EXISTS (
               SELECT 1 FROM previously_seen_messages
                WHERE previously_seen_messages.community_server_id = community_server.id
           )
           AND NOT EXISTS (
               SELECT 1 FROM note_publisher_posts
                WHERE note_publisher_posts.community_server_id = community_server.id
           )
           AND NOT EXISTS (
               SELECT 1 FROM note_publisher_config
                WHERE note_publisher_config.community_server_id = community_server.id
           )
           AND NOT EXISTS (
               SELECT 1 FROM scoring_snapshots
                WHERE scoring_snapshots.community_server_id = community_server.id
           )
           AND NOT EXISTS (
               SELECT 1 FROM simulation_orchestrators
                WHERE simulation_orchestrators.community_server_id = community_server.id
           )
           AND NOT EXISTS (
               SELECT 1 FROM simulation_runs
                WHERE simulation_runs.community_server_id = community_server.id
           )
        """
    )


def downgrade() -> None:
    """No-op: cleanup migration is destructive and idempotent."""
