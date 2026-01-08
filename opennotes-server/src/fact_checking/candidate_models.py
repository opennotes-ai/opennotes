"""SQLAlchemy models for fact-checked item candidates.

Candidates represent potential fact-check items that are pending review or
processing before being promoted to the main fact_check_items table.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import ARRAY, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from src.database import Base


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

    # Source URL for deduplication
    source_url: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    # Core content
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Rating/verdict
    # Human-approved rating (NULL until approved)
    rating: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # ML/AI predicted ratings as {rating_value: probability}
    # e.g., {"false": 0.85, "mostly_false": 0.10, "mixture": 0.05}
    # For trusted sources, set the known rating to 1.0
    predicted_ratings: Mapped[dict[str, float] | None] = mapped_column(
        JSONB, nullable=True, server_default=None
    )

    # Provenance
    published_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dataset_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    dataset_tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    original_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Flexible storage for source-specific fields
    extracted_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )

    # Processing status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=CandidateStatus.PENDING.value,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        # Unique constraint for idempotent imports
        Index(
            "idx_candidates_source_url_dataset",
            "source_url",
            "dataset_name",
            unique=True,
        ),
        # Status filtering
        Index("idx_candidates_status", "status"),
        # Dataset filtering with tags
        Index("idx_candidates_dataset_tags", "dataset_tags", postgresql_using="gin"),
        # GIN index for extracted_data queries
        Index("idx_candidates_extracted_data", "extracted_data", postgresql_using="gin"),
        # Published date for ordering
        Index("idx_candidates_published_date", "published_date"),
    )

    def __repr__(self) -> str:
        title_preview = self.title[:50] if self.title else ""
        return f"<FactCheckedItemCandidate(id={self.id}, status={self.status}, title='{title_preview}...')>"
