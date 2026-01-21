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
1. Detects Discord community_servers where platform_community_server_id is a UUID
2. Finds the "correct" row that the UUID references
3. Updates monitored_channels storing the UUID to use the correct Discord snowflake
4. Reassigns notes from duplicate to correct community_server (RESTRICT FK requires this)
5. Deletes the duplicate community_servers rows (community_members cascades)
6. Detects orphaned duplicates where the "correct" row was deleted
7. Verifies no UUID-format platform_community_server_ids remain

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

# UUID v4 pattern (matches UUIDs used as platform_community_server_id by mistake)
UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


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
              AND dup.platform_community_server_id ~ :uuid_pattern
        """),
        {"uuid_pattern": UUID_PATTERN},
    ).fetchall()

    if not duplicates:
        print("No duplicate community_servers found with UUID as platform_community_server_id")
        return

    print(f"Found {len(duplicates)} duplicate community_servers to fix")

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

        # Step 4: Delete the duplicate community_server row
        # community_members will CASCADE delete automatically
        result = conn.execute(
            sa.text("""
                DELETE FROM community_servers
                WHERE id = :duplicate_uuid
                  AND platform = 'discord'
                  AND platform_community_server_id ~ :uuid_pattern
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
              AND dup.platform_community_server_id ~ :uuid_pattern
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
              AND platform_community_server_id ~ :uuid_pattern
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
