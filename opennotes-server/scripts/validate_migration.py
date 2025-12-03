#!/usr/bin/env python3
"""
Validation script for User to Profile migration (Task 124 Phase 3).

Verifies that the migration completed successfully by checking:
- Profile/identity counts match user count
- No orphaned notes or ratings
- Participant ID patterns are migrated
- Identity uniqueness constraints hold

Usage:
    uv run python scripts/validate_migration.py
    uv run python scripts/validate_migration.py --verbose
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.notes.models import Note, Rating
from src.users.models import User
from src.users.profile_models import UserIdentity, UserProfile


class ValidationResult:
    """Track validation results."""

    def __init__(self):
        self.checks_passed = 0
        self.checks_failed = 0
        self.warnings = 0

    def pass_check(self, message: str):
        """Record a passing check."""
        self.checks_passed += 1
        print(f"✅ {message}")

    def fail_check(self, message: str):
        """Record a failing check."""
        self.checks_failed += 1
        print(f"❌ {message}")

    def warn(self, message: str):
        """Record a warning."""
        self.warnings += 1
        print(f"⚠️  {message}")

    def __repr__(self) -> str:
        status = "PASSED" if self.checks_failed == 0 else "FAILED"
        return (
            f"\n{'=' * 60}\n"
            f"Validation Summary: {status}\n"
            f"{'=' * 60}\n"
            f"Checks Passed:  {self.checks_passed}\n"
            f"Checks Failed:  {self.checks_failed}\n"
            f"Warnings:       {self.warnings}\n"
            f"{'=' * 60}\n"
        )


async def validate_migration(verbose: bool = False) -> ValidationResult:  # noqa: PLR0912 - Comprehensive validation requires many checks
    """
    Validate User to Profile migration.

    Args:
        verbose: Whether to print detailed information

    Returns:
        ValidationResult with check results
    """
    result = ValidationResult()

    print("\n" + "=" * 60)
    print("Migration Validation (Task 124 Phase 3)")
    print("=" * 60)
    print(f"Verbose: {verbose}")
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
            # Check 1: Count records
            print("📊 Checking record counts...\n")

            user_count_result = await session.execute(select(func.count(User.id)))
            user_count = user_count_result.scalar()

            profile_count_result = await session.execute(select(func.count(UserProfile.id)))
            profile_count = profile_count_result.scalar()

            identity_count_result = await session.execute(select(func.count(UserIdentity.id)))
            identity_count = identity_count_result.scalar()

            if verbose:
                print(f"  Users:      {user_count}")
                print(f"  Profiles:   {profile_count}")
                print(f"  Identities: {identity_count}\n")

            if user_count == 0:
                result.warn("No users found in database (empty database or already cleaned up)")
            elif profile_count == user_count:
                result.pass_check(f"Profile count matches user count ({profile_count})")
            else:
                result.fail_check(
                    f"Profile count ({profile_count}) does not match user count ({user_count})"
                )

            if user_count == 0:
                pass  # Already warned above
            elif identity_count == user_count:
                result.pass_check(f"Identity count matches user count ({identity_count})")
            elif identity_count > user_count:
                result.warn(
                    f"More identities ({identity_count}) than users ({user_count}) - "
                    "This is OK if users have multiple auth methods linked"
                )
            else:
                result.fail_check(
                    f"Identity count ({identity_count}) is less than user count ({user_count})"
                )

            # Check 2: Orphaned notes
            print("\n📝 Checking notes...\n")

            total_notes_result = await session.execute(select(func.count(Note.id)))
            total_notes = total_notes_result.scalar()

            orphaned_notes_result = await session.execute(
                select(func.count(Note.id)).where(Note.author_profile_id.is_(None))
            )
            orphaned_notes = orphaned_notes_result.scalar()

            if verbose:
                print(f"  Total notes:     {total_notes}")
                print(f"  Orphaned notes:  {orphaned_notes}\n")

            if orphaned_notes == 0:
                result.pass_check(
                    f"No orphaned notes (all {total_notes} notes have author_profile_id)"
                )
            else:
                result.fail_check(
                    f"Found {orphaned_notes} orphaned notes (missing author_profile_id)"
                )

                if verbose:
                    # Show sample orphaned notes
                    orphaned_sample_result = await session.execute(
                        select(Note.id, Note.author_participant_id)
                        .where(Note.author_profile_id.is_(None))
                        .limit(5)
                    )
                    orphaned_sample = orphaned_sample_result.all()
                    print("\n  Sample orphaned notes:")
                    for note_id, participant_id in orphaned_sample:
                        print(f"    Note {note_id}: participant_id = {participant_id}")
                    print()

            # Check 3: Orphaned ratings
            print("\n⭐ Checking ratings...\n")

            total_ratings_result = await session.execute(select(func.count(Rating.id)))
            total_ratings = total_ratings_result.scalar()

            orphaned_ratings_result = await session.execute(
                select(func.count(Rating.id)).where(Rating.rater_profile_id.is_(None))
            )
            orphaned_ratings = orphaned_ratings_result.scalar()

            if verbose:
                print(f"  Total ratings:     {total_ratings}")
                print(f"  Orphaned ratings:  {orphaned_ratings}\n")

            if orphaned_ratings == 0:
                result.pass_check(
                    f"No orphaned ratings (all {total_ratings} ratings have rater_profile_id)"
                )
            else:
                result.fail_check(
                    f"Found {orphaned_ratings} orphaned ratings (missing rater_profile_id)"
                )

                if verbose:
                    # Show sample orphaned ratings
                    orphaned_sample_result = await session.execute(
                        select(Rating.id, Rating.rater_participant_id)
                        .where(Rating.rater_profile_id.is_(None))
                        .limit(5)
                    )
                    orphaned_sample = orphaned_sample_result.all()
                    print("\n  Sample orphaned ratings:")
                    for rating_id, participant_id in orphaned_sample:
                        print(f"    Rating {rating_id}: participant_id = {participant_id}")
                    print()

            # Check 4: Provider distribution
            print("\n🔐 Checking identity providers...\n")

            provider_dist_result = await session.execute(
                select(UserIdentity.provider, func.count(UserIdentity.id))
                .group_by(UserIdentity.provider)
                .order_by(func.count(UserIdentity.id).desc())
            )
            provider_dist = provider_dist_result.all()

            if provider_dist:
                result.pass_check("Identity providers found:")
                for provider, count in provider_dist:
                    print(f"  - {provider}: {count}")
            else:
                result.fail_check("No identity providers found")

            # Check 5: Profile completeness
            print("\n👤 Checking profile data...\n")

            empty_display_name_result = await session.execute(
                select(func.count(UserProfile.id)).where(UserProfile.display_name == "")
            )
            empty_display_name = empty_display_name_result.scalar()

            if empty_display_name == 0:
                result.pass_check("All profiles have display names")
            else:
                result.warn(f"{empty_display_name} profiles have empty display names")

            # Check 6: Identity uniqueness
            print("\n🔑 Checking identity uniqueness...\n")

            duplicate_identities_result = await session.execute(
                select(
                    UserIdentity.provider,
                    UserIdentity.provider_user_id,
                    func.count(UserIdentity.id).label("count"),
                )
                .group_by(UserIdentity.provider, UserIdentity.provider_user_id)
                .having(func.count(UserIdentity.id) > 1)
            )
            duplicate_identities = duplicate_identities_result.all()

            if not duplicate_identities:
                result.pass_check(
                    "No duplicate identities (provider, provider_user_id) pairs are unique"
                )
            else:
                result.fail_check(f"Found {len(duplicate_identities)} duplicate identity pairs")
                if verbose:
                    print("\n  Duplicate identity pairs:")
                    for provider, provider_user_id, count in duplicate_identities[:5]:
                        print(f"    {provider}:{provider_user_id} (count: {count})")
                    print()

            # Check 7: Relationship integrity
            print("\n🔗 Checking relationships...\n")

            # Check that all identities link to valid profiles
            orphaned_identities_result = await session.execute(
                select(func.count(UserIdentity.id))
                .outerjoin(UserProfile, UserIdentity.profile_id == UserProfile.id)
                .where(UserProfile.id.is_(None))
            )
            orphaned_identities = orphaned_identities_result.scalar()

            if orphaned_identities == 0:
                result.pass_check("All identities link to valid profiles")
            else:
                result.fail_check(f"Found {orphaned_identities} identities with invalid profile_id")

    except Exception as e:
        result.fail_check(f"Validation error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        await engine.dispose()

    return result


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Validate User to Profile migration (Task 124 Phase 3)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print detailed information",
    )

    args = parser.parse_args()

    # Run validation
    result = asyncio.run(validate_migration(verbose=args.verbose))

    # Print summary
    print(result)

    # Exit with error code if validation failed
    if result.checks_failed > 0:
        print("❌ Validation FAILED - migration issues detected")
        sys.exit(1)
    else:
        print("✅ Validation PASSED - migration completed successfully")
        if result.warnings > 0:
            print(f"   ({result.warnings} warnings)")
        sys.exit(0)


if __name__ == "__main__":
    main()
