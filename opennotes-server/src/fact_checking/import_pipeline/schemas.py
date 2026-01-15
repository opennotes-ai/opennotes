"""Pydantic schemas for fact-check dataset import.

Defines models for parsing raw CSV rows from HuggingFace datasets
and normalizing them for insertion into fact_checked_item_candidates.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from src.fact_checking.candidate_models import compute_claim_hash
from src.fact_checking.import_pipeline.rating_normalizer import normalize_rating

logger = logging.getLogger(__name__)

DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"]


def _parse_review_date(review_date: str | None) -> datetime | None:
    """Parse review date from various formats to datetime."""
    if not review_date:
        return None
    try:
        return datetime.fromisoformat(review_date.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(review_date, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    logger.warning(f"Could not parse review_date: {review_date}")
    return None


def _extract_languages(claim_lang: str | None, fc_lang: str | None) -> list[str]:
    """Extract unique languages from claim and fact-check language fields."""
    languages = []
    if claim_lang:
        languages.append(claim_lang)
    if fc_lang and fc_lang != claim_lang:
        languages.append(fc_lang)
    return languages


class ClaimReviewRow(BaseModel):
    """Raw row from HuggingFace fact-check-bureau claim_reviews.csv.

    Maps directly to CSV column names without transformation.
    """

    id: int
    claim_id: int
    fact_check_id: int
    claim: str
    claimant: str | None = None
    claim_lang: str | None = None
    claim_date: str | None = None
    url: str
    title: str
    fc_lang: str | None = None
    publisher_name: str
    publisher_site: str
    review_date: str | None = None
    rating: str | None = None
    claimant_norm: str | None = None
    tweet_ids: str | None = None

    @field_validator("claim", "title", "url", mode="before")
    @classmethod
    def strip_strings(cls, v: Any) -> Any:
        """Strip whitespace from string fields."""
        if isinstance(v, str):
            return v.strip()
        return v


class NormalizedCandidate(BaseModel):
    """Validated and normalized candidate for insertion.

    Transforms raw CSV data into the schema expected by
    fact_checked_item_candidates table.

    Note: The `rating` field is intentionally NOT set during import.
    Imported ratings go to `predicted_ratings` with probability 1.0
    for trusted sources. Human approval is required to set `rating`
    before promotion to fact_check_items.
    """

    source_url: str
    claim_hash: str = Field(
        pattern=r"^[0-9a-f]{16}$",
        description="xxh3_64 hash of claim text for multi-claim deduplication (16 hex chars)",
    )
    title: str
    predicted_ratings: dict[str, float] | None = Field(
        default=None, description="ML/AI predicted ratings as {rating: probability}"
    )
    rating_details: str | None = Field(
        default=None,
        description="Original rating value when normalized to a different canonical rating",
    )
    published_date: datetime | None = None
    dataset_name: str = Field(description="Source identifier from publisher_site")
    dataset_tags: list[str] = Field(default_factory=list, description="Tags from publisher_name")
    extracted_data: dict[str, Any] = Field(
        default_factory=dict, description="Extra fields not in schema"
    )
    original_id: str = Field(description="fact_check_id from CSV as string for traceability")

    @model_validator(mode="after")
    def ensure_dataset_tags(self) -> Self:
        """Ensure dataset_tags is never empty."""
        if not self.dataset_tags:
            self.dataset_tags = [self.dataset_name]
        return self

    @classmethod
    def from_claim_review_row(cls, row: ClaimReviewRow) -> "NormalizedCandidate":
        """Create a normalized candidate from a raw CSV row.

        Performs:
        - Rating normalization (stored in predicted_ratings, not rating)
        - Date parsing
        - Field mapping to candidate schema
        - Extra data extraction to JSONB

        Note: Ratings from fact-check-bureau are from trusted sources,
        so they're stored in predicted_ratings with probability 1.0.
        The rating field remains NULL until human approval.

        Args:
            row: Validated ClaimReviewRow from CSV.

        Returns:
            NormalizedCandidate ready for database insertion.
        """
        published_date = _parse_review_date(row.review_date)
        dataset_name = row.publisher_site.lower().replace("www.", "").split("/")[0]
        dataset_tags = [row.publisher_name] if row.publisher_name else []
        languages = _extract_languages(row.claim_lang, row.fc_lang)

        tweet_ids_parsed = cls._parse_tweet_ids(row.tweet_ids)

        extracted_data = cls._build_extracted_data(row, languages, tweet_ids_parsed)

        canonical_rating, rating_details = normalize_rating(row.rating)
        predicted_ratings = {canonical_rating: 1.0} if canonical_rating else None

        return cls(
            source_url=row.url,
            claim_hash=compute_claim_hash(row.claim),
            title=row.title,
            predicted_ratings=predicted_ratings,
            rating_details=rating_details,
            published_date=published_date,
            dataset_name=dataset_name,
            dataset_tags=dataset_tags,
            extracted_data=extracted_data,
            original_id=str(row.fact_check_id),
        )

    @staticmethod
    def _parse_tweet_ids(tweet_ids: str | None) -> list[str] | None:
        """Parse tweet IDs from JSON array or comma-separated string."""
        if not tweet_ids:
            return None
        try:
            return json.loads(tweet_ids)
        except json.JSONDecodeError:
            return [tid.strip() for tid in tweet_ids.split(",") if tid.strip()]

    @staticmethod
    def _build_extracted_data(
        row: "ClaimReviewRow", languages: list[str], tweet_ids: list[str] | None
    ) -> dict[str, Any]:
        """Build the extracted_data dict from row fields."""
        extracted_data: dict[str, Any] = {
            "claim": row.claim,
            "claim_id": row.claim_id,
            "csv_id": row.id,
        }

        if row.claimant or row.claimant_norm:
            extracted_data["claimant"] = row.claimant_norm or row.claimant

        if languages:
            extracted_data["languages"] = languages

        if tweet_ids:
            extracted_data["tweet_ids"] = tweet_ids

        if row.claim_date:
            extracted_data["claim_date"] = row.claim_date

        return extracted_data
