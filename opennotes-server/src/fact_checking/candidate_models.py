"""SQLAlchemy models for fact-checked item candidates.

Candidates represent potential fact-check items that are pending review or
processing before being promoted to the main fact_check_items table.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

import xxhash
from sqlalchemy import ARRAY, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from src.database import Base


def compute_claim_hash(claim_text: str | None) -> str:
    """
    Compute xxh3_64 hash of claim text.

    Returns a 16-character hexadecimal string representing the 64-bit hash.
    Used for content-based deduplication - a single fact-check article can
    check multiple claims, each needing a separate candidate row.

    Args:
        claim_text: The claim text to hash. Empty/None becomes empty string.

    Returns:
        16-character hex string of the xxh3_64 hash.
    """
    return xxhash.xxh3_64((claim_text or "").encode()).hexdigest()


class CandidateStatus(str, Enum):
    """Status values for fact-checked item candidates."""

    PENDING = "pending"
    SCRAPING = "scraping"
    SCRAPED = "scraped"
    SCRAPE_FAILED = "scrape_failed"
    PROMOTED = "promoted"


class FactCheckedItemCandidate(Base):
    """
    Candidate fact-check items awaiting processing or review.

    Candidates are created during bulk imports or crawling operations. They go
    through a pipeline:
    1. pending - Initial state after import/crawl
    2. scraping - Content scraping in progress
    3. scraped - Content successfully scraped
    4. scrape_failed - Content scraping failed
    5. promoted - Successfully promoted to fact_check_items table

    Rating Workflow:
    - `rating` is the human-approved verdict (NULL until approved)
    - `predicted_ratings` stores ML/AI predictions as {rating: probability}
    - Sources with known reliable ratings may have predicted_ratings[rating]=1.0
    - Promotion requires both content AND rating (human approval)
    - Bulk approval workflows can set rating from predicted_ratings

    Attributes:
        id: Unique identifier (UUID v7)
        source_url: URL to the original article (used for deduplication)
        title: Article title from source
        content: Scraped article body (NULL until scraped)
        summary: Optional summary (typically generated later)
        rating: Human-approved fact-check verdict (NULL until approved)
        predicted_ratings: JSONB mapping rating values to probability estimates
        published_date: Publication date from source
        dataset_name: Source identifier (e.g., publisher_site)
        dataset_tags: Tags for filtering (e.g., publisher_name)
        original_id: ID from source dataset for traceability
        extracted_data: JSONB for source-specific fields not in schema
        status: Processing status (pending, scraping, scraped, scrape_failed, promoted)
        error_message: Error details if scrape_failed
        created_at: Timestamp when record was created
        updated_at: Timestamp of last update
    """

    __tablename__ = "fact_checked_item_candidates"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
        index=True,
    )

    # Source URL for deduplication (indexed via __table_args__)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)

    # Hash of claim text for multi-claim deduplication
    # A single fact-check article can check multiple claims
    claim_hash: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="xxh3_64 hash of claim text for multi-claim deduplication",
    )

    # Core content
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Rating/verdict
    # Human-approved rating (NULL until approved)
    rating: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Original rating value when normalized to a different canonical rating
    # e.g., "missing_context" when rating is "misleading", "altered" when rating is "false"
    rating_details: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # ML/AI predicted ratings as {rating_value: probability}
    # e.g., {"false": 0.85, "mostly_false": 0.10, "mixture": 0.05}
    # For trusted sources, set the known rating to 1.0
    predicted_ratings: Mapped[dict[str, float] | None] = mapped_column(
        JSONB, nullable=True, server_default=None
    )

    # Provenance (indexed via __table_args__)
    published_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dataset_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dataset_tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    original_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Flexible storage for source-specific fields
    extracted_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )

    # Processing status (indexed via __table_args__)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=CandidateStatus.PENDING.value,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Note: onupdate callback only fires for ORM-level attribute changes.
    # Direct SQL updates (via SQLAlchemy's update() construct) must explicitly
    # set updated_at=func.now(). A database trigger was considered but would be
    # inconsistent with other models in the codebase that use this same pattern.
    # Refer to the scrape_tasks and promotion modules in import_pipeline.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        # Unique constraint for idempotent imports (includes claim_hash for multi-claim articles)
        Index(
            "idx_candidates_source_url_claim_hash_dataset",
            "source_url",
            "claim_hash",
            "dataset_name",
            unique=True,
        ),
        # Single-column indexes for common queries
        Index("idx_candidates_source_url", "source_url"),
        Index("idx_candidates_claim_hash", "claim_hash"),
        Index("idx_candidates_dataset_name", "dataset_name"),
        Index("idx_candidates_original_id", "original_id"),
        Index("idx_candidates_status", "status"),
        Index("idx_candidates_published_date", "published_date"),
        # GIN indexes for array/JSONB columns
        Index("idx_candidates_dataset_tags", "dataset_tags", postgresql_using="gin"),
        Index("idx_candidates_extracted_data", "extracted_data", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        title_preview = self.title[:50] if self.title else ""
        return f"<FactCheckedItemCandidate(id={self.id}, status={self.status}, title='{title_preview}...')>"
