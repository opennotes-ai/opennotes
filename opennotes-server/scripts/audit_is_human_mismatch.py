"""Audit script for Phase 1.2a: find is_human=False profiles with principal_type='human' Users.

Queries for UserProfile rows where is_human=False whose backing User (reached via
UserIdentity) has principal_type='human'. This indicates a data inconsistency between
the legacy is_human flag and the new principal_type column.

This is a REPORT ONLY script — it makes no changes to the database.

Usage:
    cd opennotes/opennotes-server && uv run python scripts/audit_is_human_mismatch.py
"""

import asyncio

from sqlalchemy import text

from src.database import get_engine


async def main() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        result = await conn.execute(
            text("""
            SELECT
                p.id          AS profile_id,
                p.display_name,
                p.is_human,
                u.id          AS user_id,
                u.username,
                u.principal_type
            FROM user_profiles p
            JOIN user_identities ui ON ui.profile_id = p.id
            JOIN users u ON (
                (ui.provider = 'discord' AND ui.provider_user_id = u.discord_id) OR
                (ui.provider = 'email'   AND ui.provider_user_id = u.email)
            )
            WHERE p.is_human = FALSE
              AND u.principal_type = 'human'
            ORDER BY p.id
        """)
        )
        rows = result.fetchall()

    if not rows:
        print("No mismatches found.")
    else:
        print(f"Found {len(rows)} mismatch(es):")
        for row in rows:
            print(
                f"  Profile {row.profile_id} ({row.display_name}): "
                f"is_human=False but User {row.user_id} ({row.username}) "
                f"has principal_type='{row.principal_type}'"
            )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
