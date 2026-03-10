"""
Backfill missing titles in message_metadata for MessageArchive records.

Finds records with source_url but no title, fetches the page title via
trafilatura metadata extraction, and updates the JSONB field in-place.

Usage:
    cd opennotes-server && uv run python -m src.notes.backfill_titles
"""

from __future__ import annotations

import asyncio
import logging

import trafilatura
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import JSONB
from trafilatura.metadata import extract_metadata

from src.database import close_db, get_session_maker
from src.notes.message_archive_models import MessageArchive
from src.shared.content_extraction import get_random_user_agent

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MAX_CONCURRENT = 5
FETCH_TIMEOUT = 30


def fetch_title(url: str) -> str | None:
    try:
        user_agent = get_random_user_agent()
        config = trafilatura.settings.use_config()  # pyright: ignore[reportAttributeAccessIssue]
        config.set("DEFAULT", "USER_AGENT", user_agent)
        downloaded = trafilatura.fetch_url(url, config=config)
        if not downloaded:
            return None
        meta = extract_metadata(downloaded, default_url=url)
        if meta and meta.title:
            return str(meta.title)
    except Exception:
        logger.debug("Failed to fetch title for %s", url)
    return None


async def fetch_title_async(url: str) -> str | None:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(fetch_title, url),
            timeout=FETCH_TIMEOUT,
        )
    except (TimeoutError, Exception):
        return None


async def backfill() -> None:
    session_maker = get_session_maker()

    async with session_maker() as session:
        stmt = select(MessageArchive.id, MessageArchive.message_metadata).where(
            MessageArchive.deleted_at.is_(None),
            MessageArchive.message_metadata.isnot(None),
            MessageArchive.message_metadata.cast(JSONB)["source_url"].astext != "",
        )
        result = await session.execute(stmt)
        rows = result.all()

    candidates = []
    for row in rows:
        meta = row.message_metadata
        if not isinstance(meta, dict):
            continue
        source_url = meta.get("source_url")
        title = meta.get("title")
        if source_url and (not title or title == ""):
            candidates.append((row.id, source_url))

    logger.info("Found %d records needing title backfill", len(candidates))
    if not candidates:
        return

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    updated = 0
    failed = 0

    async def process(archive_id, url):  # pyright: ignore[reportMissingParameterType,reportUnknownParameterType]
        nonlocal updated, failed
        async with semaphore:
            title = await fetch_title_async(url)
            if not title:
                failed += 1
                logger.warning("No title for %s (archive %s)", url, archive_id)
                return

            async with session_maker() as session:
                await session.execute(
                    text(
                        "UPDATE message_archive "
                        "SET message_metadata = jsonb_set(message_metadata, '{title}', :title::jsonb), "
                        "    updated_at = now() "
                        "WHERE id = :id"
                    ),
                    {"id": archive_id, "title": f'"{title}"'},
                )
                await session.commit()
            updated += 1
            logger.info("Updated archive %s: %s", archive_id, title)

    tasks = [process(aid, url) for aid, url in candidates]
    await asyncio.gather(*tasks)

    logger.info("Backfill complete: %d updated, %d failed", updated, failed)
    await close_db()


def main() -> None:
    asyncio.run(backfill())


if __name__ == "__main__":
    main()
