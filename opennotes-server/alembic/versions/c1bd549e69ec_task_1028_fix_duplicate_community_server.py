"""task_1028_fix_duplicate_community_server

Fix duplicate CommunityServer rows caused by GuildSetupService.ts passing UUID
instead of Discord snowflake to the monitored channels API.

Bug: GuildSetupService.registerChannels() passed the resolved community server UUID
instead of the Discord guild ID (snowflake) when creating monitored channels. This
caused verify_community_admin() -> get_community_server_by_platform_id(uuid, auto_create=True)
to create a duplicate community_servers row with the UUID as platform_community_server_id.

Pattern detected:
- Row A (correct): id=<uuid-A>, platform_community_server_id=<discord-snowflake>
- Row B (buggy):   id=<uuid-B>, platform_community_server_id=<uuid-A> (UUID instead of snowflake!)

This migration:
1. Detects Discord community_servers where platform_community_server_id is a UUID (case-insensitive)
2. Finds the "correct" row that the UUID references
3. Updates monitored_channels storing the UUID to use the correct Discord snowflake
4. Reassigns notes from duplicate to correct community_server (RESTRICT FK requires this)
5. Reassigns requests from duplicate to correct community_server (SET NULL FK - preserve data)
6. Updates webhooks storing the UUID to use the correct Discord snowflake
7. Updates interactions storing the UUID to use the correct Discord snowflake
8. Reassigns bulk_content_scan_logs from duplicate to correct community_server (CASCADE FK - preserve data)
9. Migrates community_config from duplicate to correct (most recent updated_at wins for conflicts)
10. Logs CASCADE-delete counts for audit trail (community_members, previously_seen_messages,
    community_server_llm_config, llm_usage_log)
11. Deletes the duplicate community_servers rows (CASCADE deletes noted tables)
12. Detects orphaned duplicates where the "correct" row was deleted
13. Verifies no UUID-format platform_community_server_ids remain

CASCADE delete decisions (acceptable data loss):
- community_members: Membership records for duplicate server; duplicate was never real
- previously_seen_messages: URL tracking for duplicate detection; no real messages existed
- community_server_llm_config: LLM API configs; would conflict with correct server's configs
- llm_usage_log: Usage statistics; low-value historical data for buggy duplicate

Revision ID: c1bd549e69ec
Revises: task_1009_rating_len
Create Date: 2026-01-21 11:30:20.455187

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1bd549e69ec"
down_revision: str | Sequence[str] | None = "task_1009_rating_len"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# UUID pattern (matches any standard UUID format - v1, v4, v5, v7, etc.)
# Using case-insensitive pattern to catch both lowercase and uppercase UUIDs
UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


def upgrade() -> None:
    """Fix duplicate community servers where platform_community_server_id is a UUID.

    This migration is idempotent - safe to run multiple times.
    Detects the pattern dynamically rather than hardcoding specific UUIDs.
    """
    conn = op.get_bind()

    # Step 1: Find all Discord community_servers where platform_community_server_id
    # looks like a UUID (the buggy duplicates)
    duplicates = conn.execute(
        sa.text("""
            SELECT
                dup.id AS duplicate_id,
                dup.platform_community_server_id AS incorrect_platform_id,
                correct.id AS correct_id,
                correct.platform_community_server_id AS correct_snowflake
            FROM community_servers dup
            JOIN community_servers correct
                ON correct.id::text = dup.platform_community_server_id
                AND correct.platform = 'discord'
            WHERE dup.platform = 'discord'
              AND dup.platform_community_server_id ~* :uuid_pattern
        """),
        {"uuid_pattern": UUID_PATTERN},
    ).fetchall()

    if not duplicates:
        print("No duplicate community_servers found with UUID as platform_community_server_id")
        return

    print(f"Found {len(duplicates)} duplicate community_servers to fix")

    # Pre-processing detection: Count affected rows in CASCADE tables
    # This helps understand the scope of data that will be migrated/preserved
    duplicate_ids = [dup.duplicate_id for dup in duplicates]

    total_bulk_scan_count = 0
    total_config_count = 0
    for dup_id in duplicate_ids:
        bulk_scan_count = conn.execute(
            sa.text("""
                SELECT COUNT(*) as count
                FROM bulk_content_scan_logs
                WHERE community_server_id = :dup_id
            """),
            {"dup_id": dup_id},
        ).scalar()
        total_bulk_scan_count += bulk_scan_count

        config_count = conn.execute(
            sa.text("""
                SELECT COUNT(*) as count
                FROM community_config
                WHERE community_server_id = :dup_id
            """),
            {"dup_id": dup_id},
        ).scalar()
        total_config_count += config_count

    print(f"  bulk_content_scan_logs rows referencing duplicates: {total_bulk_scan_count}")
    print(f"  community_config rows referencing duplicates: {total_config_count}")

    if total_bulk_scan_count > 0 or total_config_count > 0:
        print("  These rows will be migrated to correct community_servers (not lost)")

    for dup in duplicates:
        duplicate_id = dup.duplicate_id
        correct_id = dup.correct_id
        incorrect_platform_id = dup.incorrect_platform_id
        correct_snowflake = dup.correct_snowflake

        print(f"  Fixing duplicate {duplicate_id}:")
        print(f"    incorrect platform_community_server_id: {incorrect_platform_id}")
        print(f"    correct community_server.id: {correct_id}")
        print(f"    correct Discord snowflake: {correct_snowflake}")

        # Step 2: Fix monitored_channels that have the UUID instead of Discord snowflake
        result = conn.execute(
            sa.text("""
                UPDATE monitored_channels
                SET community_server_id = :correct_snowflake
                WHERE community_server_id = :incorrect_uuid
            """),
            {
                "correct_snowflake": correct_snowflake,
                "incorrect_uuid": incorrect_platform_id,
            },
        )
        print(f"    Updated {result.rowcount} monitored_channels rows")

        # Step 3: Reassign notes from duplicate to correct community_server
        # notes.community_server_id has ondelete="RESTRICT" so we must update before delete
        result = conn.execute(
            sa.text("""
                UPDATE notes
                SET community_server_id = :correct_id
                WHERE community_server_id = :duplicate_id
            """),
            {
                "correct_id": correct_id,
                "duplicate_id": duplicate_id,
            },
        )
        print(f"    Reassigned {result.rowcount} notes to correct community_server")

        # Step 3b: Reassign requests from duplicate to correct community_server
        # requests.community_server_id has ondelete="SET NULL" but we want to preserve the FK
        result = conn.execute(
            sa.text("""
                UPDATE requests
                SET community_server_id = :correct_id
                WHERE community_server_id = :duplicate_id
            """),
            {
                "correct_id": correct_id,
                "duplicate_id": duplicate_id,
            },
        )
        print(f"    Reassigned {result.rowcount} requests to correct community_server")

        # Step 3c: Fix webhooks that may have stored the buggy UUID instead of Discord snowflake
        # webhooks.community_server_id is a String(50) storing platform IDs
        result = conn.execute(
            sa.text("""
                UPDATE webhooks
                SET community_server_id = :correct_snowflake
                WHERE community_server_id = :incorrect_uuid
            """),
            {
                "correct_snowflake": correct_snowflake,
                "incorrect_uuid": incorrect_platform_id,
            },
        )
        print(f"    Updated {result.rowcount} webhooks rows")

        # Step 3d: Fix interactions that may have stored the buggy UUID instead of Discord snowflake
        # interactions.community_server_id is a String(50) storing platform IDs
        result = conn.execute(
            sa.text("""
                UPDATE interactions
                SET community_server_id = :correct_snowflake
                WHERE community_server_id = :incorrect_uuid
            """),
            {
                "correct_snowflake": correct_snowflake,
                "incorrect_uuid": incorrect_platform_id,
            },
        )
        print(f"    Updated {result.rowcount} interactions rows")

        # Step 3e: Reassign bulk_content_scan_logs from duplicate to correct community_server
        # bulk_content_scan_logs.community_server_id has ondelete="CASCADE" but we preserve data
        result = conn.execute(
            sa.text("""
                UPDATE bulk_content_scan_logs
                SET community_server_id = :correct_id
                WHERE community_server_id = :duplicate_id
            """),
            {
                "correct_id": correct_id,
                "duplicate_id": duplicate_id,
            },
        )
        print(
            f"    Reassigned {result.rowcount} bulk_content_scan_logs to correct community_server"
        )

        # Step 3f: Migrate community_config from duplicate to correct
        # community_config has composite PK (community_server_id, config_key) with CASCADE delete
        # Strategy: migrate unique configs, update overlapping if duplicate is newer

        # First, migrate configs that exist ONLY in duplicate (not in correct)
        result = conn.execute(
            sa.text("""
                UPDATE community_config
                SET community_server_id = :correct_id
                WHERE community_server_id = :duplicate_id
                  AND config_key NOT IN (
                      SELECT config_key FROM community_config WHERE community_server_id = :correct_id
                  )
            """),
            {
                "correct_id": correct_id,
                "duplicate_id": duplicate_id,
            },
        )
        migrated_unique_configs = result.rowcount
        print(
            f"    Migrated {migrated_unique_configs} unique community_config entries from duplicate"
        )

        # For overlapping config_keys, update correct's config if duplicate has newer updated_at
        # Log which configs will be updated vs discarded
        overlapping = conn.execute(
            sa.text("""
                SELECT
                    dup.config_key,
                    dup.updated_at AS dup_updated_at,
                    correct.updated_at AS correct_updated_at,
                    CASE WHEN dup.updated_at > correct.updated_at THEN 'duplicate' ELSE 'correct' END AS kept
                FROM community_config dup
                JOIN community_config correct
                    ON correct.config_key = dup.config_key
                    AND correct.community_server_id = :correct_id
                WHERE dup.community_server_id = :duplicate_id
            """),
            {
                "correct_id": correct_id,
                "duplicate_id": duplicate_id,
            },
        ).fetchall()

        if overlapping:
            kept_from_duplicate = sum(1 for row in overlapping if row.kept == "duplicate")
            kept_from_correct = sum(1 for row in overlapping if row.kept == "correct")
            print(f"    Found {len(overlapping)} overlapping config keys:")
            print(f"      - {kept_from_duplicate} will be updated from duplicate (newer)")
            print(f"      - {kept_from_correct} will be kept from correct (newer or equal)")
            for row in overlapping:
                print(
                    f"      config_key={row.config_key}: kept {row.kept} "
                    f"(dup={row.dup_updated_at}, correct={row.correct_updated_at})"
                )

        # Update correct's configs where duplicate has newer updated_at
        result = conn.execute(
            sa.text("""
                UPDATE community_config AS target
                SET config_value = source.config_value,
                    updated_at = source.updated_at,
                    updated_by = source.updated_by
                FROM community_config AS source
                WHERE target.community_server_id = :correct_id
                  AND source.community_server_id = :duplicate_id
                  AND target.config_key = source.config_key
                  AND source.updated_at > target.updated_at
            """),
            {
                "correct_id": correct_id,
                "duplicate_id": duplicate_id,
            },
        )
        print(
            f"    Updated {result.rowcount} community_config entries with newer values from duplicate"
        )

        # Step 4: Delete the duplicate community_server row
        # Log CASCADE-delete counts for audit trail before deletion
        # These tables have CASCADE FK and their data will be deleted (acceptable data loss):
        # - community_members: Membership records for buggy duplicate
        # - previously_seen_messages: URL tracking data (duplicate never had real messages)
        # - community_server_llm_config: Would conflict with correct server's configs
        # - llm_usage_log: Low-value historical data for buggy duplicate
        cascade_counts = conn.execute(
            sa.text("""
                SELECT
                    (SELECT COUNT(*) FROM community_members WHERE community_id = :dup_id) AS members,
                    (SELECT COUNT(*) FROM previously_seen_messages WHERE community_server_id = :dup_id) AS prev_seen,
                    (SELECT COUNT(*) FROM community_server_llm_config WHERE community_server_id = :dup_id) AS llm_cfg,
                    (SELECT COUNT(*) FROM llm_usage_log WHERE community_server_id = :dup_id) AS llm_usage
            """),
            {"dup_id": duplicate_id},
        ).fetchone()
        print(
            f"    CASCADE delete counts: community_members={cascade_counts.members}, "
            f"previously_seen_messages={cascade_counts.prev_seen}, "
            f"community_server_llm_config={cascade_counts.llm_cfg}, "
            f"llm_usage_log={cascade_counts.llm_usage}"
        )

        result = conn.execute(
            sa.text("""
                DELETE FROM community_servers
                WHERE id = :duplicate_uuid
                  AND platform = 'discord'
                  AND platform_community_server_id ~* :uuid_pattern
            """),
            {
                "duplicate_uuid": duplicate_id,
                "uuid_pattern": UUID_PATTERN,
            },
        )
        print(f"    Deleted {result.rowcount} duplicate community_servers rows")

    # Step 5: Detect orphaned duplicates (UUID-format platform_id with no matching correct row)
    # This handles edge cases where the "correct" row was somehow deleted
    orphans = conn.execute(
        sa.text("""
            SELECT
                dup.id AS orphan_id,
                dup.platform_community_server_id AS orphan_platform_id
            FROM community_servers dup
            WHERE dup.platform = 'discord'
              AND dup.platform_community_server_id ~* :uuid_pattern
              AND NOT EXISTS (
                  SELECT 1 FROM community_servers correct
                  WHERE correct.id::text = dup.platform_community_server_id
              )
        """),
        {"uuid_pattern": UUID_PATTERN},
    ).fetchall()

    if orphans:
        print(f"WARNING: Found {len(orphans)} orphaned duplicates (correct row was deleted):")
        for orphan in orphans:
            print(
                f"  - id={orphan.orphan_id}, platform_community_server_id={orphan.orphan_platform_id}"
            )
        print(
            "  These need manual investigation - the referenced community_server no longer exists"
        )

    # Step 6: Post-migration verification - confirm no UUID-format platform_community_server_ids remain
    remaining = conn.execute(
        sa.text("""
            SELECT COUNT(*) as count
            FROM community_servers
            WHERE platform = 'discord'
              AND platform_community_server_id ~* :uuid_pattern
        """),
        {"uuid_pattern": UUID_PATTERN},
    ).scalar()

    if remaining == 0:
        print(
            "Verification passed: No community_servers with UUID-format platform_community_server_id remain"
        )
    else:
        print(
            f"WARNING: {remaining} community_servers still have UUID-format platform_community_server_id"
        )
        print("  This may indicate orphaned duplicates that need manual investigation")


def downgrade() -> None:
    """Cannot undo data corruption fix.

    This migration fixes corrupted data. Reversing it would re-corrupt the data,
    which is not desirable. The downgrade is intentionally a no-op.
    """
    print("Downgrade is a no-op - cannot undo data corruption fix")
