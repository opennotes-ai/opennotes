#!/usr/bin/env python3
import asyncio
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import ARRAY, CheckConstraint, Index, String, Text, insert, select
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

BATCH_SIZE = 500
DATASET_NAME = "snopes"
DATASET_TAGS = ["snopes", "fact-check", "misinformation"]


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


def validate_row(row: pd.Series, row_num: int) -> dict[str, Any] | None:
    """
    Validate and transform a single row from the Snopes dataset.

    Args:
        row: Pandas Series representing a single row
        row_num: Row number for error reporting

    Returns:
        Dict with transformed data if valid, None if invalid
    """
    try:
        if pd.isna(row.get("question")) or pd.isna(row.get("claim")):
            logger.warning(f"Row {row_num}: Missing required fields (question or claim)")
            return None

        title = str(row["question"]).strip()
        claim = str(row["claim"]).strip()

        if not title or not claim:
            logger.warning(f"Row {row_num}: Empty title or claim after stripping")
            return None

        origin_text = str(row.get("origin", "")) if pd.notna(row.get("origin")) else ""
        summary_text = str(row.get("summary", "")) if pd.notna(row.get("summary")) else ""

        content = f"{claim}\n\n{origin_text}".strip()

        rating = str(row.get("rate", "")).strip() if pd.notna(row.get("rate")) else None
        author = None

        metadata = {
            "comment": str(row.get("comment", "")) if pd.notna(row.get("comment")) else None,
            "whats_true": str(row.get("what's true", ""))
            if pd.notna(row.get("what's true"))
            else None,
            "whats_false": str(row.get("what's false", ""))
            if pd.notna(row.get("what's false"))
            else None,
            "whats_unknown": str(row.get("what's unknown", ""))
            if pd.notna(row.get("what's unknown"))
            else None,
        }

        metadata = {k: v for k, v in metadata.items() if v}

        return {
            "dataset_name": DATASET_NAME,
            "dataset_tags": DATASET_TAGS,
            "title": title,
            "content": content,
            "summary": summary_text if summary_text else None,
            "source_url": None,
            "original_id": None,
            "published_date": None,
            "author": author,
            "rating": rating,
            "embedding": None,
            "extra_metadata": metadata,
        }

    except Exception as e:
        logger.error(f"Row {row_num}: Validation error - {e}")
        return None


async def clear_existing_snopes_data(session: AsyncSession) -> int:
    """
    Clear existing Snopes data from the database.

    Args:
        session: Async database session

    Returns:
        Number of rows deleted
    """
    result = await session.execute(
        select(FactCheckItem).where(FactCheckItem.dataset_name == DATASET_NAME)
    )
    existing = result.scalars().all()
    count = len(existing)

    if count > 0:
        logger.info(f"Clearing {count} existing Snopes records")
        for item in existing:
            await session.delete(item)
        await session.flush()

    return count


async def load_snopes_dataset(csv_path: Path, clear_existing: bool = True) -> tuple[int, int]:
    """
    Load Snopes dataset into the fact_check_items table.

    Args:
        csv_path: Path to the snopeswithsum.csv file
        clear_existing: If True, delete existing Snopes data before loading

    Returns:
        Tuple of (rows_loaded, rows_skipped)
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {csv_path}")

    logger.info(f"Loading Snopes dataset from: {csv_path}")

    df = pd.read_csv(csv_path)
    logger.info(f"Read {len(df)} rows from CSV")

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    rows_loaded = 0
    rows_skipped = 0

    async with async_session() as session, session.begin():
        if clear_existing:
            deleted_count = await clear_existing_snopes_data(session)
            logger.info(f"Deleted {deleted_count} existing Snopes records")

        valid_rows = []

        for idx, row in df.iterrows():
            validated = validate_row(row, idx + 1)
            if validated:
                valid_rows.append(validated)
            else:
                rows_skipped += 1

        logger.info(f"Validated {len(valid_rows)} rows ({rows_skipped} skipped)")

        for i in range(0, len(valid_rows), BATCH_SIZE):
            batch = valid_rows[i : i + BATCH_SIZE]

            await session.execute(insert(FactCheckItem), batch)

            rows_loaded += len(batch)
            logger.info(
                f"Inserted batch {i // BATCH_SIZE + 1}: {rows_loaded}/{len(valid_rows)} rows"
            )

        logger.info("Committing transaction...")

    await engine.dispose()

    logger.info(f"Dataset loading complete: {rows_loaded} rows loaded, {rows_skipped} rows skipped")
    return rows_loaded, rows_skipped


async def verify_load(expected_count: int) -> None:
    """
    Verify that data was loaded correctly.

    Args:
        expected_count: Expected number of rows in the database
    """
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession)

    async with async_session() as session:
        result = await session.execute(
            select(FactCheckItem).where(FactCheckItem.dataset_name == DATASET_NAME)
        )
        items = result.scalars().all()
        count = len(items)

        logger.info(f"Verification: Found {count} Snopes records in database")

        if count != expected_count:
            logger.warning(f"Expected {expected_count} rows, found {count}")
        else:
            logger.info("Verification successful!")

        if count > 0:
            sample = items[0]
            logger.info(f"Sample record: {sample.title[:100]}...")
            logger.info(f"  - Rating: {sample.rating}")
            logger.info(f"  - Tags: {sample.dataset_tags}")
            logger.info(f"  - Metadata keys: {list(sample.extra_metadata.keys())}")

    await engine.dispose()


async def main() -> None:
    """Main entry point for the script."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    csv_path = project_root / "data" / "datasets" / "snopeswithsum.csv"

    logger.info("=" * 80)
    logger.info("Snopes Dataset Loading Pipeline")
    logger.info("=" * 80)

    start_time = datetime.now(UTC)

    try:
        rows_loaded, _rows_skipped = await load_snopes_dataset(csv_path, clear_existing=True)

        logger.info("Verifying data load...")
        await verify_load(rows_loaded)

        elapsed = datetime.now(UTC) - start_time
        logger.info(f"Total time: {elapsed.total_seconds():.2f} seconds")
        logger.info(f"Load rate: {rows_loaded / elapsed.total_seconds():.2f} rows/second")

    except Exception as e:
        logger.error(f"Failed to load dataset: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
