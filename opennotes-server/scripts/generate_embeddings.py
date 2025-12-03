#!/usr/bin/env python3
import asyncio
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI, RateLimitError
from sqlalchemy import ARRAY, CheckConstraint, Index, String, Text, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import DateTime

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None

from uuid import UUID, uuid4

from src.config import get_settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 100
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1.0
MAX_RETRY_DELAY = 60.0
TOKENS_PER_EMBEDDING_ESTIMATE = 8


class Base(DeclarativeBase):
    pass


class FactCheckItem(Base):
    __tablename__ = "fact_check_items"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, index=True
    )

    dataset_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    dataset_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, index=True)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)

    rating: Mapped[str | None] = mapped_column(String(50), nullable=True)

    embedding: Mapped[Any | None] = mapped_column(Vector(1536) if Vector else None, nullable=True)

    embedding_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="NOW()", onupdate=datetime.utcnow
    )

    __table_args__ = (
        CheckConstraint("array_length(dataset_tags, 1) > 0", name="check_dataset_tags_not_empty"),
        Index("idx_fact_check_items_dataset_name", "dataset_name"),
        Index("idx_fact_check_items_dataset_tags", "dataset_tags", postgresql_using="gin"),
        Index("idx_fact_check_items_metadata", "metadata", postgresql_using="gin"),
        Index("idx_fact_check_items_published_date", "published_date"),
        Index("idx_fact_check_items_dataset_name_tags", "dataset_name", "dataset_tags"),
    )


async def generate_embeddings_with_retry(
    client: AsyncOpenAI, texts: list[str], max_retries: int = MAX_RETRIES
) -> list[list[float]]:
    """
    Generate embeddings for a batch of texts with exponential backoff retry.

    Args:
        client: AsyncOpenAI client instance
        texts: List of texts to generate embeddings for
        max_retries: Maximum number of retry attempts

    Returns:
        List of embedding vectors

    Raises:
        Exception: If all retries are exhausted
    """
    retry_delay = INITIAL_RETRY_DELAY

    for attempt in range(max_retries):
        try:
            response = await client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=texts,
            )

            return [item.embedding for item in response.data]

        except RateLimitError:
            if attempt < max_retries - 1:
                logger.warning(
                    f"Rate limit hit. Retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
            else:
                logger.error(f"Rate limit exceeded after {max_retries} attempts")
                raise

        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            if attempt < max_retries - 1:
                logger.warning(
                    f"Retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
            else:
                raise

    raise Exception(f"Failed to generate embeddings after {max_retries} attempts")


async def fetch_items_without_embeddings(
    session: AsyncSession, dataset_name: str, limit: int | None = None
) -> list[FactCheckItem]:
    """
    Fetch items that need embeddings generated.

    Args:
        session: Database session
        dataset_name: Dataset to process (e.g., 'snopes')
        limit: Optional limit on number of items to fetch

    Returns:
        List of FactCheckItem objects
    """
    query = select(FactCheckItem).where(
        FactCheckItem.dataset_name == dataset_name, FactCheckItem.embedding.is_(None)
    )

    if limit:
        query = query.limit(limit)

    result = await session.execute(query)
    return list(result.scalars().all())


async def update_embeddings(
    session: AsyncSession, item_ids: list[UUID], embeddings: list[list[float]]
) -> None:
    """
    Update database records with generated embeddings.

    Args:
        session: Database session
        item_ids: List of item IDs to update
        embeddings: List of embedding vectors
    """
    for item_id, embedding in zip(item_ids, embeddings, strict=False):
        await session.execute(
            update(FactCheckItem)
            .where(FactCheckItem.id == item_id)
            .values(
                embedding=embedding, embedding_provider="openai", embedding_model=EMBEDDING_MODEL
            )
        )


def estimate_cost(total_items: int, avg_content_length: int) -> tuple[int, float]:
    """
    Estimate OpenAI API cost for embedding generation.

    Args:
        total_items: Number of items to process
        avg_content_length: Average content length in characters

    Returns:
        Tuple of (estimated_tokens, estimated_cost_usd)
    """
    tokens_per_char = 0.25
    estimated_tokens = int(total_items * avg_content_length * tokens_per_char)

    cost_per_million_tokens = 0.02
    estimated_cost = (estimated_tokens / 1_000_000) * cost_per_million_tokens

    return estimated_tokens, estimated_cost


async def generate_embeddings_for_dataset(
    dataset_name: str, openai_api_key: str, batch_size: int = BATCH_SIZE, limit: int | None = None
) -> tuple[int, int]:
    """
    Generate embeddings for all items in a dataset that don't have them yet.

    Args:
        dataset_name: Name of the dataset to process
        openai_api_key: OpenAI API key
        batch_size: Number of items to process per batch
        limit: Optional limit on total items to process

    Returns:
        Tuple of (items_processed, items_failed)
    """
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    client = AsyncOpenAI(api_key=openai_api_key)

    items_processed = 0
    items_failed = 0
    start_time = time.time()

    async with async_session() as session, session.begin():
        items = await fetch_items_without_embeddings(session, dataset_name, limit)

        total_items = len(items)
        logger.info(f"Found {total_items} items without embeddings")

        if total_items == 0:
            logger.info("No items to process")
            return 0, 0

        avg_content_length = sum(len(item.content) for item in items) // total_items
        estimated_tokens, estimated_cost = estimate_cost(total_items, avg_content_length)

        logger.info(f"Estimated tokens: {estimated_tokens:,}")
        logger.info(f"Estimated cost: ${estimated_cost:.4f}")
        logger.info(f"Processing {total_items} items in batches of {batch_size}")

        for i in range(0, total_items, batch_size):
            batch = items[i : i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_items + batch_size - 1) // batch_size

            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} items)")

            texts = [item.content for item in batch]
            item_ids = [item.id for item in batch]

            try:
                embeddings = await generate_embeddings_with_retry(client, texts)

                await update_embeddings(session, item_ids, embeddings)

                items_processed += len(batch)

                elapsed = time.time() - start_time
                rate = items_processed / elapsed if elapsed > 0 else 0
                remaining = total_items - items_processed
                eta = remaining / rate if rate > 0 else 0

                logger.info(
                    f"Progress: {items_processed}/{total_items} "
                    f"({items_processed / total_items * 100:.1f}%) "
                    f"| Rate: {rate:.1f} items/s "
                    f"| ETA: {eta:.0f}s"
                )

            except Exception as e:
                logger.error(f"Failed to process batch {batch_num}: {e}")
                items_failed += len(batch)
                continue

        logger.info("Committing transaction...")

    await engine.dispose()

    elapsed = time.time() - start_time
    logger.info(f"Processing complete in {elapsed:.2f}s")
    logger.info(f"Items processed: {items_processed}")
    logger.info(f"Items failed: {items_failed}")

    return items_processed, items_failed


async def verify_embeddings(dataset_name: str) -> None:
    """
    Verify that embeddings were generated successfully.

    Args:
        dataset_name: Dataset to verify
    """
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession)

    async with async_session() as session:
        result = await session.execute(
            select(FactCheckItem).where(
                FactCheckItem.dataset_name == dataset_name, FactCheckItem.embedding.is_not(None)
            )
        )
        items_with_embeddings = result.scalars().all()

        result = await session.execute(
            select(FactCheckItem).where(
                FactCheckItem.dataset_name == dataset_name, FactCheckItem.embedding.is_(None)
            )
        )
        items_without_embeddings = result.scalars().all()

        total = len(items_with_embeddings) + len(items_without_embeddings)

        logger.info(f"Verification for dataset '{dataset_name}':")
        logger.info(f"  Total items: {total}")
        logger.info(f"  With embeddings: {len(items_with_embeddings)}")
        logger.info(f"  Without embeddings: {len(items_without_embeddings)}")

        if items_with_embeddings:
            sample = items_with_embeddings[0]
            embedding_length = len(sample.embedding) if sample.embedding else 0
            logger.info(f"  Sample embedding dimensions: {embedding_length}")

    await engine.dispose()


async def main() -> None:
    """Main entry point for the script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate OpenAI embeddings for fact-checking dataset"
    )
    parser.add_argument(
        "--dataset", type=str, default="snopes", help="Dataset name to process (default: snopes)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=f"Batch size for API calls (default: {BATCH_SIZE})",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit number of items to process (default: all)"
    )
    parser.add_argument(
        "--verify-only", action="store_true", help="Only verify embeddings, don't generate new ones"
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("OpenAI Embedding Generation Pipeline")
    logger.info("=" * 80)

    openai_api_key = None
    try:
        settings = get_settings()
        openai_api_key = getattr(settings, "OPENAI_API_KEY", None)
    except Exception:
        pass

    if not openai_api_key:
        import os

        openai_api_key = os.getenv("OPENAI_API_KEY")

    if not openai_api_key and not args.verify_only:
        logger.error("OPENAI_API_KEY not found in environment or settings")
        logger.error("Set OPENAI_API_KEY environment variable or add to .env file")
        sys.exit(1)

    if args.verify_only:
        await verify_embeddings(args.dataset)
    else:
        _items_processed, items_failed = await generate_embeddings_for_dataset(
            dataset_name=args.dataset,
            openai_api_key=openai_api_key,
            batch_size=args.batch_size,
            limit=args.limit,
        )

        logger.info("Verifying embeddings...")
        await verify_embeddings(args.dataset)

        if items_failed > 0:
            logger.warning(f"Some items failed to process: {items_failed}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
