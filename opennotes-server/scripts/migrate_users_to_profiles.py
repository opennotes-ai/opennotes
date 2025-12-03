#!/usr/bin/env python3
"""
Data migration script for Task 124 Phase 3: User to Profile Migration

Migrates existing User records to the new UserProfile + UserIdentity structure:
- Each User becomes a UserProfile
- Authentication credentials become UserIdentity records
- Note and Rating authorship links are updated to use profile IDs

Usage:
    # Dry run (preview changes without committing)
    uv run python scripts/migrate_users_to_profiles.py --dry-run

    # Execute migration with default batch size (100)
    uv run python scripts/migrate_users_to_profiles.py

    # Execute migration with custom batch size
    uv run python scripts/migrate_users_to_profiles.py --batch-size 50

    # Verbose output
    uv run python scripts/migrate_users_to_profiles.py --verbose
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.notes.models import Note, Rating
from src.users.models import User
from src.users.profile_models import UserIdentity, UserProfile


class MigrationStats:
    """Track migration statistics."""

    def __init__(self):
        self.users_processed = 0
        self.profiles_created = 0
        self.identities_created = 0
        self.notes_updated = 0
        self.ratings_updated = 0
        self.errors = 0
        self.start_time = datetime.now(UTC)

    def __repr__(self) -> str:
        elapsed = (datetime.now(UTC) - self.start_time).total_seconds()
        return (
            f"\n{'=' * 60}\n"
            f"Migration Summary\n"
            f"{'=' * 60}\n"
            f"Users Processed:       {self.users_processed}\n"
            f"Profiles Created:      {self.profiles_created}\n"
            f"Identities Created:    {self.identities_created}\n"
            f"Notes Updated:         {self.notes_updated}\n"
            f"Ratings Updated:       {self.ratings_updated}\n"
            f"Errors:                {self.errors}\n"
            f"Elapsed Time:          {elapsed:.2f}s\n"
            f"{'=' * 60}\n"
        )


async def determine_auth_provider(user: User) -> tuple[str, str]:
    """
    Determine authentication provider and provider_user_id from User record.

    Args:
        user: User model instance

    Returns:
        Tuple of (provider, provider_user_id)

    Raises:
        ValueError: If no authentication method can be determined
    """
    # Priority order: discord_id > username > email
    if user.discord_id:
        return ("discord", user.discord_id)

    # For users without discord_id, use username as provider_user_id
    # Provider will be "local" to indicate traditional username/password auth
    if user.username:
        return ("local", user.username)

    # Fallback to email if username is not set (edge case)
    if user.email:
        return ("email", user.email)

    raise ValueError(f"Cannot determine authentication provider for user {user.id}")


async def migrate_user_to_profile(  # noqa: PLR0912 - Migration logic requires many validation branches
    session: AsyncSession, user: User, verbose: bool = False
) -> tuple[UUID, UUID, int, int]:
    """
    Migrate a single User to UserProfile + UserIdentity structure.

    Args:
        session: Database session
        user: User model instance to migrate
        verbose: Whether to print detailed progress

    Returns:
        Tuple of (profile_id, identity_id, notes_updated_count, ratings_updated_count)

    Raises:
        ValueError: If user data is invalid or migration fails
    """
    if verbose:
        print(f"\n→ Migrating user {user.id}: {user.username}")

    # Step 1: Create UserProfile
    display_name = user.full_name or user.username
    profile = UserProfile(
        display_name=display_name,
        is_human=True,  # All existing users are human
        reputation=0,  # Starting reputation
        created_at=user.created_at.replace(tzinfo=None),
        updated_at=user.updated_at.replace(tzinfo=None) if user.updated_at else None,
    )
    session.add(profile)
    await session.flush()  # Get profile.id
    if verbose:
        print(f"  ✓ Created profile {profile.id} (display_name: {profile.display_name})")

    # Step 2: Create UserIdentity
    try:
        provider, provider_user_id = await determine_auth_provider(user)
    except ValueError as e:
        raise ValueError(f"Failed to determine auth provider for user {user.id}: {e}")

    # Build credentials JSON based on provider
    credentials: dict[str, Any] = {}
    if provider == "discord":
        credentials = {
            "discord_id": user.discord_id,
            "username": user.username,
            "email": user.email,
        }
    elif provider == "local":
        credentials = {
            "username": user.username,
            "email": user.email,
            "hashed_password": user.hashed_password,
        }
    elif provider == "email":
        credentials = {
            "email": user.email,
            "hashed_password": user.hashed_password,
        }

    identity = UserIdentity(
        profile_id=profile.id,
        provider=provider,
        provider_user_id=provider_user_id,
        credentials=credentials,
        created_at=user.created_at.replace(tzinfo=None),
        updated_at=user.updated_at.replace(tzinfo=None) if user.updated_at else None,
    )
    session.add(identity)
    await session.flush()
    if verbose:
        print(f"  ✓ Created identity {identity.id} (provider: {provider})")

    # Step 3: Build participant_id for Note/Rating lookup
    # Legacy participant_id format varies, we need to handle common patterns:
    # - Discord: "discord:{discord_id}" or just discord_id
    # - Local: "local:{username}" or just username
    participant_id_patterns = []

    if user.discord_id:
        participant_id_patterns.extend(
            [
                f"discord:{user.discord_id}",
                user.discord_id,
            ]
        )

    if user.username:
        participant_id_patterns.extend(
            [
                f"local:{user.username}",
                user.username,
            ]
        )

    if user.email:
        participant_id_patterns.extend(
            [
                f"email:{user.email}",
                user.email,
            ]
        )

    # Step 4: Update Note.author_profile_id where author_participant_id matches
    notes_updated = 0
    for pattern in participant_id_patterns:
        result = await session.execute(
            update(Note)
            .where(Note.author_participant_id == pattern)
            .where(Note.author_profile_id.is_(None))  # Only update if not already set
            .values(author_profile_id=profile.id)
        )
        notes_updated += result.rowcount

    if verbose and notes_updated > 0:
        print(f"  ✓ Updated {notes_updated} notes with author_profile_id")

    # Step 5: Update Rating.rater_profile_id where rater_participant_id matches
    ratings_updated = 0
    for pattern in participant_id_patterns:
        result = await session.execute(
            update(Rating)
            .where(Rating.rater_participant_id == pattern)
            .where(Rating.rater_profile_id.is_(None))  # Only update if not already set
            .values(rater_profile_id=profile.id)
        )
        ratings_updated += result.rowcount

    if verbose and ratings_updated > 0:
        print(f"  ✓ Updated {ratings_updated} ratings with rater_profile_id")

    return (profile.id, identity.id, notes_updated, ratings_updated)


async def migrate_all_users(
    batch_size: int = 100, dry_run: bool = False, verbose: bool = False
) -> MigrationStats:
    """
    Migrate all users from User to UserProfile + UserIdentity structure.

    Args:
        batch_size: Number of users to process per batch
        dry_run: If True, rollback changes instead of committing
        verbose: Whether to print detailed progress

    Returns:
        MigrationStats object with migration results
    """
    stats = MigrationStats()

    print("\n" + "=" * 60)
    print("User to Profile Migration (Task 124 Phase 3)")
    print("=" * 60)
    print(
        f"Mode:       {'DRY RUN (no changes will be committed)' if dry_run else 'LIVE MIGRATION'}"
    )
    print(f"Batch Size: {batch_size}")
    print(f"Verbose:    {verbose}")
    print("=" * 60 + "\n")

    # Create async engine and session
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )

    async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session_maker() as session:
            # Query all users
            result = await session.execute(select(User).order_by(User.id))
            all_users = result.scalars().all()

            total_users = len(all_users)
            print(f"Found {total_users} users to migrate\n")

            if total_users == 0:
                print("No users to migrate.")
                return stats

            # Process users in batches
            for i in range(0, total_users, batch_size):
                batch = all_users[i : i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (total_users + batch_size - 1) // batch_size

                print(f"\n[Batch {batch_num}/{total_batches}] Processing {len(batch)} users...")

                for user in batch:
                    try:
                        (
                            _profile_id,
                            _identity_id,
                            notes_count,
                            ratings_count,
                        ) = await migrate_user_to_profile(session, user, verbose)

                        stats.users_processed += 1
                        stats.profiles_created += 1
                        stats.identities_created += 1
                        stats.notes_updated += notes_count
                        stats.ratings_updated += ratings_count

                        # Show progress without details
                        if not verbose and stats.users_processed % 10 == 0:
                            print(f"  Processed {stats.users_processed}/{total_users} users...")

                    except Exception as e:
                        stats.errors += 1
                        print(f"  ✗ ERROR migrating user {user.id}: {e}")
                        if verbose:
                            import traceback

                            traceback.print_exc()
                        # Continue with next user
                        continue

                print(f"[Batch {batch_num}/{total_batches}] Completed")

            # Commit or rollback based on dry_run flag
            if dry_run:
                print("\n→ DRY RUN: Rolling back all changes...")
                await session.rollback()
            else:
                print("\n→ Committing changes to database...")
                await session.commit()
                print("✓ Changes committed successfully")

    except Exception as e:
        print(f"\n✗ FATAL ERROR during migration: {e}")
        import traceback

        traceback.print_exc()
        stats.errors += 1

    finally:
        await engine.dispose()

    return stats


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate User records to UserProfile + UserIdentity structure (Task 124 Phase 3)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Dry run (preview changes)
    uv run python scripts/migrate_users_to_profiles.py --dry-run

    # Execute migration
    uv run python scripts/migrate_users_to_profiles.py

    # Execute with custom batch size and verbose output
    uv run python scripts/migrate_users_to_profiles.py --batch-size 50 --verbose
        """,
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of users to process per batch (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without committing to database",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print detailed progress for each user",
    )

    args = parser.parse_args()

    # Validate batch size
    if args.batch_size < 1:
        print("ERROR: --batch-size must be at least 1")
        sys.exit(1)

    # Run migration
    stats = asyncio.run(
        migrate_all_users(
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
    )

    # Print summary
    print(stats)

    # Exit with error code if there were errors
    if stats.errors > 0:
        print(f"\n⚠️  Migration completed with {stats.errors} errors")
        sys.exit(1)
    else:
        print("\n✅ Migration completed successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()
