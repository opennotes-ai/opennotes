"""
Backfill missing titles in message_metadata for MessageArchive records.

Finds records with source_url but no title, fetches the page title via
trafilatura metadata extraction, and updates the JSONB field in-place.

Usage:
    cd opennotes-server && uv run python -m src.notes.backfill_titles
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

import trafilatura
from sqlalchemy import or_, select, text
from sqlalchemy.dialects.postgresql import JSONB
from trafilatura.metadata import extract_metadata

from src.database import close_db, get_session_maker
from src.notes.message_archive_models import MessageArchive
from src.shared.content_extraction import get_random_user_agent

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MAX_CONCURRENT = 5
FETCH_TIMEOUT = 30
BATCH_SIZE = 500


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
    except Exception:
        return None


def _build_candidates_query(last_id: UUID | None = None):  # pyright: ignore[reportUnknownParameterType]
    stmt = select(MessageArchive.id, MessageArchive.message_metadata).where(
        MessageArchive.deleted_at.is_(None),
        MessageArchive.message_metadata.isnot(None),
        MessageArchive.message_metadata.cast(JSONB)["source_url"].astext != "",
        or_(
            ~MessageArchive.message_metadata.cast(JSONB).has_key("title"),
            MessageArchive.message_metadata.cast(JSONB)["title"].astext == "",
        ),
    )
    if last_id is not None:
        stmt = stmt.where(MessageArchive.id > last_id)
    return stmt.order_by(MessageArchive.id).limit(BATCH_SIZE)


async def backfill() -> None:
    session_maker = get_session_maker()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    total_updated = 0
    total_failed = 0
    last_id: UUID | None = None

    while True:
        async with session_maker() as session:
            stmt = _build_candidates_query(last_id)
            result = await session.execute(stmt)
            rows = result.all()

        if not rows:
            break

        candidates: list[tuple[UUID, str]] = []
        for row in rows:
            meta = row.message_metadata
            if not isinstance(meta, dict):
                continue
            source_url = meta.get("source_url")
            if source_url:
                candidates.append((row.id, source_url))

        last_id = rows[-1].id

        if not candidates:
            continue

        logger.info("Processing batch of %d candidates", len(candidates))

        batch_updated = 0
        batch_failed = 0

        async def process(archive_id: UUID, url: str) -> None:
            nonlocal batch_updated, batch_failed
            async with semaphore:
                title = await fetch_title_async(url)
                if not title:
                    batch_failed += 1
                    logger.warning("No title for %s (archive %s)", url, archive_id)
                    return

                try:
                    async with session_maker() as session:
                        await session.execute(
                            text(
                                "UPDATE message_archive "
                                "SET message_metadata = jsonb_set(message_metadata, '{title}', :title::jsonb), "
                                "    updated_at = now() "
                                "WHERE id = :id"
                            ),
                            {"id": archive_id, "title": json.dumps(title)},
                        )
                        await session.commit()
                    batch_updated += 1
                    logger.info("Updated archive %s: %s", archive_id, title)
                except Exception:
                    batch_failed += 1
                    logger.exception("Failed to update archive %s", archive_id)

        tasks = [process(aid, url) for aid, url in candidates]
        await asyncio.gather(*tasks, return_exceptions=True)

        total_updated += batch_updated
        total_failed += batch_failed

    logger.info("Backfill complete: %d updated, %d failed", total_updated, total_failed)
    await close_db()


def main() -> None:
    asyncio.run(backfill())


if __name__ == "__main__":
    main()
