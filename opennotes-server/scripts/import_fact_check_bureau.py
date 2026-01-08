#!/usr/bin/env python
"""Import fact-check-bureau dataset from HuggingFace.

This script provides CLI access to the fact-check import pipeline.

Usage:
    # Full import (idempotent)
    uv run python scripts/import_fact_check_bureau.py

    # Dry run (validate only)
    uv run python scripts/import_fact_check_bureau.py --dry-run

    # Enqueue scrape tasks for pending candidates
    uv run python scripts/import_fact_check_bureau.py --enqueue-scrapes

    # Custom batch size
    uv run python scripts/import_fact_check_bureau.py --batch-size 500
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.database import get_db
from src.fact_checking.import_pipeline.importer import import_fact_check_bureau
from src.fact_checking.import_pipeline.scrape_task import enqueue_scrape_batch
from src.monitoring.logging import setup_logging


async def main() -> int:
    """Run the import script."""
    parser = argparse.ArgumentParser(
        description="Import fact-check-bureau dataset from HuggingFace"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only, do not insert into database",
    )
    parser.add_argument(
        "--enqueue-scrapes",
        action="store_true",
        help="Enqueue scrape tasks for pending candidates",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Batch size for import/scrape operations (default: 1000)",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Override dataset URL (for testing)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    settings = get_settings()
    setup_logging(
        log_level="DEBUG" if args.verbose else settings.LOG_LEVEL,
        json_format=False,
        service_name="import-fact-check-bureau",
    )

    logger = logging.getLogger(__name__)

    if args.enqueue_scrapes:
        logger.info("Enqueueing scrape tasks for pending candidates...")
        result = await enqueue_scrape_batch(batch_size=args.batch_size)
        logger.info(f"Enqueued {result['enqueued']} scrape tasks")
        return 0

    logger.info("Starting fact-check-bureau import...")
    if args.dry_run:
        logger.info("DRY RUN: No data will be inserted")

    async for session in get_db():
        stats = await import_fact_check_bureau(
            session=session,
            batch_size=args.batch_size,
            url=args.url,
            dry_run=args.dry_run,
        )

        logger.info("=" * 60)
        logger.info("Import Summary")
        logger.info("=" * 60)
        logger.info(f"Total rows:    {stats.total_rows}")
        logger.info(f"Valid rows:    {stats.valid_rows}")
        logger.info(f"Invalid rows:  {stats.invalid_rows}")
        logger.info(f"Inserted:      {stats.inserted}")
        logger.info(f"Updated:       {stats.updated}")

        if stats.errors:
            logger.warning(f"Errors (first 10): {len(stats.errors)}")
            for error in stats.errors[:10]:
                logger.warning(f"  - {error}")

        if stats.invalid_rows > 0:
            logger.warning(f"Validation errors: {stats.invalid_rows} rows failed validation")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
