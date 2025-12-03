#!/usr/bin/env python3
"""
Backfill script to generate AI descriptions for existing image attachments.

Usage:
    python scripts/backfill_image_descriptions.py [--limit N] [--dry-run] [--batch-size N]

Options:
    --limit N         Process only N images (default: all)
    --dry-run         Show what would be processed without making changes
    --batch-size N    Process images in batches of N (default: 10)
    --detail LEVEL    Vision detail level: low, high, auto (default: auto)
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from src.config import settings
from src.database import async_session_maker
from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.service import LLMService
from src.monitoring import get_logger
from src.notes.message_archive_models import ContentType, MessageArchive
from src.services.vision_service import VisionService

logger = get_logger(__name__)


async def get_images_without_descriptions(db, limit: int | None = None):
    """Get image archives that don't have descriptions yet."""
    stmt = (
        select(MessageArchive)
        .where(
            MessageArchive.content_type == ContentType.IMAGE,
            MessageArchive.image_description.is_(None),
            MessageArchive.deleted_at.is_(None),
        )
        .order_by(MessageArchive.created_at.desc())
    )

    if limit:
        stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    return result.scalars().all()


async def backfill_image_description(
    db,
    vision_service: VisionService,
    archive: MessageArchive,
    detail: str = "auto",
    dry_run: bool = False,
) -> tuple[bool, str | None]:
    """
    Generate and save description for a single image archive.

    Returns:
        Tuple of (success: bool, error_message: str | None)
    """
    if not archive.content_url:
        return False, "No content URL"

    if dry_run:
        logger.info(f"[DRY RUN] Would process image: {archive.id} - {archive.content_url[:100]}")
        return True, None

    try:
        if not archive.discord_channel_id:
            logger.warning(
                f"No discord_channel_id for archive {archive.id}, skipping",
                extra={"archive_id": str(archive.id)},
            )
            return False, "No discord_channel_id (cannot determine community_server_id)"

        description = await vision_service.describe_image(
            db=db,
            image_url=archive.content_url,
            community_server_id=archive.discord_channel_id,
            detail=detail,
        )

        archive.image_description = description
        await db.flush()

        logger.info(
            f"Generated description for image {archive.id}",
            extra={
                "archive_id": str(archive.id),
                "image_url": archive.content_url[:100],
                "description_length": len(description),
            },
        )

        return True, None

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e!s}"
        logger.error(
            f"Failed to generate description for image {archive.id}",
            extra={
                "archive_id": str(archive.id),
                "image_url": archive.content_url[:100],
                "error": error_msg,
            },
        )
        return False, error_msg


async def backfill_images(
    limit: int | None = None,
    dry_run: bool = False,
    batch_size: int = 10,
    detail: str = "auto",
):
    """Main backfill function."""
    logger.info(
        "Starting image description backfill",
        extra={
            "limit": limit,
            "dry_run": dry_run,
            "batch_size": batch_size,
            "detail": detail,
        },
    )

    encryption_service = EncryptionService(settings.ENCRYPTION_MASTER_KEY)
    client_manager = LLMClientManager(encryption_service)
    llm_service = LLMService(client_manager)
    vision_service = VisionService(llm_service)

    try:
        async with async_session_maker() as db:
            images = await get_images_without_descriptions(db, limit)

            total_count = len(images)
            logger.info(f"Found {total_count} images without descriptions")

            if dry_run:
                logger.info("[DRY RUN] No changes will be made")

            success_count = 0
            error_count = 0
            errors = []

            for i in range(0, len(images), batch_size):
                batch = images[i : i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (len(images) + batch_size - 1) // batch_size

                logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} images)")

                for archive in batch:
                    success, error = await backfill_image_description(
                        db, vision_service, archive, detail, dry_run
                    )

                    if success:
                        success_count += 1
                    else:
                        error_count += 1
                        errors.append({"archive_id": str(archive.id), "error": error})

                if not dry_run and batch_num % 5 == 0:
                    await db.commit()
                    logger.info(f"Committed batch {batch_num}")

                await asyncio.sleep(1)

            if not dry_run:
                await db.commit()
                logger.info("Final commit completed")

            logger.info(
                "Backfill completed",
                extra={
                    "total": total_count,
                    "success": success_count,
                    "errors": error_count,
                    "dry_run": dry_run,
                },
            )

            if errors:
                logger.warning(
                    f"Encountered {len(errors)} errors during backfill",
                    extra={"errors": errors[:10]},
                )
    finally:
        pass


def main():
    """Parse arguments and run backfill."""
    parser = argparse.ArgumentParser(
        description="Backfill AI descriptions for existing image attachments"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Process only N images (default: all)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without making changes",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Process images in batches of N (default: 10)",
    )
    parser.add_argument(
        "--detail",
        type=str,
        default="auto",
        choices=["low", "high", "auto"],
        help="Vision detail level (default: auto)",
    )

    args = parser.parse_args()

    asyncio.run(
        backfill_images(
            limit=args.limit, dry_run=args.dry_run, batch_size=args.batch_size, detail=args.detail
        )
    )


if __name__ == "__main__":
    main()
