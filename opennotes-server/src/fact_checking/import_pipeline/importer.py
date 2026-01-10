"""Bulk import service for fact-check datasets.

Provides streaming import of CSV datasets from HuggingFace with:
- Batch processing for memory efficiency
- Idempotent upserts via ON CONFLICT
- Progress logging for large datasets
- Validation and error handling
"""

import csv
import io
import logging
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.fact_checking.candidate_models import FactCheckedItemCandidate
from src.fact_checking.import_pipeline.schemas import ClaimReviewRow, NormalizedCandidate

logger = logging.getLogger(__name__)

HUGGINGFACE_DATASET_URL = (
    "https://huggingface.co/datasets/NaughtyConstrictor/fact-check-bureau/"
    "resolve/main/claim_reviews.csv"
)


@dataclass
class ImportStats:
    """Statistics from an import run."""

    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    inserted: int = 0
    updated: int = 0
    errors: list[str] | None = None


def batched(iterable: Iterator[Any], batch_size: int) -> Iterator[list[Any]]:
    """Yield successive batches from an iterator."""
    batch: list[Any] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def parse_csv_rows(content: str) -> Iterator[dict[str, Any]]:
    """Parse CSV content into dictionaries."""
    reader = csv.DictReader(io.StringIO(content))
    yield from reader


def validate_and_normalize_batch(
    rows: list[dict[str, Any]],
) -> tuple[list[NormalizedCandidate], list[str]]:
    """Validate and normalize a batch of CSV rows.

    Returns:
        Tuple of (valid candidates, error messages)
    """
    candidates: list[NormalizedCandidate] = []
    errors: list[str] = []

    for row in rows:
        try:
            claim_review = ClaimReviewRow(**row)
            candidate = NormalizedCandidate.from_claim_review_row(claim_review)
            candidates.append(candidate)
        except ValidationError as e:
            row_id = row.get("id", "unknown")
            errors.append(f"Row {row_id}: {e}")
        except Exception as e:
            row_id = row.get("id", "unknown")
            errors.append(f"Row {row_id}: Unexpected error - {e}")

    return candidates, errors


async def upsert_candidates(
    session: AsyncSession,
    candidates: list[NormalizedCandidate],
) -> tuple[int, int]:
    """Insert or update candidates in database.

    Uses PostgreSQL ON CONFLICT to handle duplicates idempotently.
    Uses RETURNING with xmax to distinguish inserts from updates:
    - xmax = 0 means the row was inserted (no previous transaction modified it)
    - xmax > 0 means the row was updated (previous transaction's ID stored in xmax)

    Args:
        session: Database session.
        candidates: List of normalized candidates to upsert.

    Returns:
        Tuple of (inserted_count, updated_count)
    """
    if not candidates:
        return 0, 0

    values = [
        {
            "source_url": c.source_url,
            "claim_hash": c.claim_hash,
            "title": c.title,
            "predicted_ratings": c.predicted_ratings,
            "published_date": c.published_date,
            "dataset_name": c.dataset_name,
            "dataset_tags": c.dataset_tags,
            "extracted_data": c.extracted_data,
            "original_id": c.original_id,
        }
        for c in candidates
    ]

    stmt = insert(FactCheckedItemCandidate).values(values)

    stmt = stmt.on_conflict_do_update(
        index_elements=["source_url", "claim_hash", "dataset_name"],
        set_={
            "title": stmt.excluded.title,
            "predicted_ratings": stmt.excluded.predicted_ratings,
            "published_date": stmt.excluded.published_date,
            "dataset_tags": stmt.excluded.dataset_tags,
            "extracted_data": stmt.excluded.extracted_data,
            "updated_at": text("now()"),
        },
    ).returning(FactCheckedItemCandidate.id, text("xmax"))

    result = await session.execute(stmt)
    rows = result.fetchall()
    await session.commit()

    inserted_count = 0
    updated_count = 0
    for row in rows:
        xmax = row[1]
        if xmax == 0:
            inserted_count += 1
        else:
            updated_count += 1

    return inserted_count, updated_count


async def stream_csv_from_url(url: str) -> AsyncIterator[str]:
    """Stream CSV content from a URL in chunks.

    Yields the full content as we need to parse CSV which requires
    complete rows. For truly large files, consider using aiofiles
    with temporary storage.
    """
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        yield response.text


async def import_fact_check_bureau(
    session: AsyncSession,
    batch_size: int = 1000,
    url: str | None = None,
    dry_run: bool = False,
) -> ImportStats:
    """Import fact-check-bureau dataset from HuggingFace.

    Streams the CSV, validates rows, and performs batch upserts
    for idempotent import of ~230k claim-review pairs.

    Args:
        session: Database session for inserts.
        batch_size: Number of rows per batch (default 1000).
        url: Override URL for testing.
        dry_run: If True, validate only without inserting.

    Returns:
        ImportStats with counts and any errors.
    """
    dataset_url = url or HUGGINGFACE_DATASET_URL
    stats = ImportStats(errors=[])

    logger.info(f"Starting import from {dataset_url}")

    try:
        async for content in stream_csv_from_url(dataset_url):
            rows = list(parse_csv_rows(content))
            stats.total_rows = len(rows)
            logger.info(f"Loaded {stats.total_rows} rows from CSV")

            for batch_num, batch in enumerate(batched(iter(rows), batch_size)):
                candidates, errors = validate_and_normalize_batch(batch)
                stats.valid_rows += len(candidates)
                stats.invalid_rows += len(errors)

                if errors and stats.errors is not None:
                    stats.errors.extend(errors[:10])

                if not dry_run and candidates:
                    inserted, updated = await upsert_candidates(session, candidates)
                    stats.inserted += inserted
                    stats.updated += updated

                processed = (batch_num + 1) * batch_size
                if processed % 10000 == 0 or processed >= stats.total_rows:
                    logger.info(
                        f"Progress: {min(processed, stats.total_rows)}/{stats.total_rows} rows "
                        f"({stats.valid_rows} valid, {stats.invalid_rows} invalid)"
                    )

    except httpx.HTTPError as e:
        error_msg = f"HTTP error fetching dataset: {e}"
        logger.error(error_msg)
        if stats.errors is not None:
            stats.errors.append(error_msg)
    except Exception as e:
        error_msg = f"Import failed: {e}"
        logger.exception(error_msg)
        if stats.errors is not None:
            stats.errors.append(error_msg)

    logger.info(
        f"Import complete: {stats.total_rows} total, {stats.valid_rows} valid, "
        f"{stats.inserted} inserted, {stats.updated} updated"
    )

    return stats
