#!/usr/bin/env python3
"""
Migration script to migrate existing Request.original_message_content to MessageArchive.

This script:
1. Finds Request records with original_message_content but no message_archive_id
2. Creates MessageArchive records with the content
3. Links the Request to the new MessageArchive
4. Marks the Request as migrated (migrated_from_content = True)

Usage:
    # Dry run to see what would be migrated
    uv run python scripts/migrate_message_content_to_archive.py --dry-run

    # Actually perform migration
    uv run python scripts/migrate_message_content_to_archive.py

    # Custom batch size
    uv run python scripts/migrate_message_content_to_archive.py --batch-size 500
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings
from src.notes.message_archive_models import ContentType, MessageArchive
from src.notes.models import Request


class MigrationStats:
    """Track migration statistics."""

    def __init__(self) -> None:
        self.total_to_migrate = 0
        self.total_migrated = 0
        self.total_errors = 0
        self.start_time = datetime.now(UTC)

    def print_summary(self) -> None:
        """Print final migration summary."""
        elapsed = (datetime.now(UTC) - self.start_time).total_seconds()
        print("\n" + "=" * 70)
        print("MIGRATION SUMMARY")
        print("=" * 70)
        print(f"Total records to migrate: {self.total_to_migrate}")
        print(f"Successfully migrated:    {self.total_migrated}")
        print(f"Errors:                   {self.total_errors}")
        print(f"Time elapsed:             {elapsed:.2f} seconds")
        if self.total_migrated > 0:
            print(f"Rate:                     {self.total_migrated / elapsed:.2f} records/sec")
        print("=" * 70)


async def count_records_to_migrate(session: AsyncSession) -> int:
    """Count total number of Request records that need migration.

    Args:
        session: Database session

    Returns:
        Number of records needing migration
    """
    stmt = select(func.count(Request.id)).where(
        and_(
            Request.original_message_content.isnot(None),
            Request.message_archive_id.is_(None),
            Request.migrated_from_content.is_(False),
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def migrate_batch(
    session: AsyncSession,
    offset: int,
    limit: int,
    dry_run: bool = False,
) -> int:
    """Migrate a batch of Request records to MessageArchive.

    Args:
        session: Database session
        offset: Starting offset for batch
        limit: Maximum number of records to process in this batch
        dry_run: If True, don't commit changes

    Returns:
        Number of records successfully migrated in this batch
    """
    # Query Request records needing migration
    stmt = (
        select(Request)
        .where(
            and_(
                Request.original_message_content.isnot(None),
                Request.message_archive_id.is_(None),
                Request.migrated_from_content.is_(False),
            )
        )
        .offset(offset)
        .limit(limit)
    )

    result = await session.execute(stmt)
    requests = result.scalars().all()

    if not requests:
        return 0

    migrated_count = 0

    for request in requests:
        try:
            # Create MessageArchive record with content from Request
            message_archive = MessageArchive(
                content_type=ContentType.TEXT,
                content_text=request.original_message_content,
                # Set created_at to match the request timestamp
                created_at=request.requested_at,
                # Add metadata tracking migration source
                message_metadata={
                    "migrated_from": "request.original_message_content",
                    "migration_timestamp": datetime.now(UTC).isoformat(),
                    "request_id": request.request_id,
                },
            )

            # Add the archive record
            session.add(message_archive)
            await session.flush()  # Flush to get the generated UUID

            # Update Request to reference the new archive
            request.message_archive_id = message_archive.id
            request.migrated_from_content = True

            migrated_count += 1

            if not dry_run:
                # Commit after each record to avoid losing progress on errors
                await session.commit()

        except Exception as e:
            print(f"ERROR migrating request {request.request_id}: {e}")
            await session.rollback()
            continue

    return migrated_count


async def migrate_all(
    batch_size: int = 1000,
    dry_run: bool = False,
) -> MigrationStats:
    """Migrate all Request records to MessageArchive in batches.

    Args:
        batch_size: Number of records to process per batch
        dry_run: If True, don't commit changes

    Returns:
        MigrationStats object with summary information
    """
    stats = MigrationStats()

    # Create async engine and session
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )

    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_maker() as session:
        # Count total records to migrate
        stats.total_to_migrate = await count_records_to_migrate(session)

        if stats.total_to_migrate == 0:
            print("No records found to migrate.")
            return stats

        print(f"\nFound {stats.total_to_migrate} records to migrate")
        print(f"Batch size: {batch_size}")
        print(f"Dry run: {dry_run}")
        print("-" * 70)

        # Process in batches
        offset = 0
        batch_num = 1

        while offset < stats.total_to_migrate:
            print(f"\nProcessing batch {batch_num} (offset {offset})...")

            migrated = await migrate_batch(
                session=session,
                offset=offset,
                limit=batch_size,
                dry_run=dry_run,
            )

            stats.total_migrated += migrated

            # Calculate and display progress
            progress_pct = (stats.total_migrated / stats.total_to_migrate) * 100
            print(f"  Migrated {migrated}/{batch_size} records in this batch")
            print(
                f"  Overall progress: {stats.total_migrated}/{stats.total_to_migrate} "
                f"({progress_pct:.1f}%)"
            )

            offset += batch_size
            batch_num += 1

            # In dry run mode, stop after first batch to show example
            if dry_run and batch_num > 1:
                print("\n(Dry run mode - stopping after first batch)")
                break

    await engine.dispose()
    return stats


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Migrate Request.original_message_content to MessageArchive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of records to process per batch (default: 1000)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without committing changes",
    )

    return parser.parse_args()


async def main() -> None:
    """Main entry point."""
    args = parse_args()

    print("\n" + "=" * 70)
    print("MESSAGE CONTENT TO ARCHIVE MIGRATION")
    print("=" * 70)

    if args.dry_run:
        print("\n*** DRY RUN MODE - No changes will be committed ***\n")

    # Run migration
    stats = await migrate_all(
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )

    # Print summary
    stats.print_summary()

    if args.dry_run:
        print("\nDry run complete. Run without --dry-run to perform actual migration.")
    else:
        print("\nMigration complete!")

    # Exit with error code if there were errors
    sys.exit(1 if stats.total_errors > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
