from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID

from src.config import settings
from src.fact_checking.embedding_schemas import FactCheckMatch as IndexedFactCheckMatch
from src.url_content_scan.claims_schemas import ClaimsReport, FactCheckMatch

DEFAULT_KNOWN_MISINFO_LIMIT = 5
FACT_CHECK_EMBEDDING_DIMENSIONS = 1536


class KnownMisinfoLookup(Protocol):
    async def lookup(self, claim_text: str) -> list[FactCheckMatch]: ...


@dataclass(slots=True)
class EmbeddingServiceKnownMisinfoAdapter:
    """Adapter onto the existing fact-check embedding index.

    This keeps URL-scan retrieval on the same query-time embedding path as the
    imported fact-check corpus: `EmbeddingService.similarity_search()` generates
    a query embedding through `LLMService` and searches the existing chunked
    fact-check index. TASK-1487.13 can inject the concrete DB/session context.
    """

    embedding_service: Any
    db: Any
    community_server_id: str
    community_server_uuid: UUID | None = None
    dataset_tags: list[str] = field(default_factory=list)
    similarity_threshold: float | None = None
    score_threshold: float = 0.1
    limit: int = DEFAULT_KNOWN_MISINFO_LIMIT
    expected_embedding_model: str = field(
        default_factory=lambda: settings.EMBEDDING_MODEL.to_pydantic_ai()
    )
    expected_embedding_dimensions: int = field(
        default_factory=lambda: settings.EMBEDDING_DIMENSIONS
    )

    async def lookup(self, claim_text: str) -> list[FactCheckMatch]:
        self._validate_embedding_context()
        response = await self.embedding_service.similarity_search(
            db=self.db,
            query_text=claim_text,
            community_server_id=self.community_server_id,
            dataset_tags=self.dataset_tags,
            similarity_threshold=self.similarity_threshold,
            score_threshold=self.score_threshold,
            limit=self.limit,
            community_server_uuid=self.community_server_uuid,
        )
        return [
            FactCheckMatch(
                claim_text=claim_text,
                publisher=match.author or match.dataset_name,
                review_title=match.title,
                review_url=match.source_url or "",
                textual_rating=match.rating or "",
                review_date=_to_review_date(match.published_date),
            )
            for match in response.matches
        ]

    def _validate_embedding_context(self) -> None:
        if self.community_server_uuid is None and not self.community_server_id.strip():
            raise ValueError("community_server_id is required for known-misinfo lookup")
        if self.expected_embedding_dimensions != FACT_CHECK_EMBEDDING_DIMENSIONS:
            raise ValueError(
                "known-misinfo lookup requires the fact-check index dimension "
                f"{FACT_CHECK_EMBEDDING_DIMENSIONS}, got {self.expected_embedding_dimensions}"
            )

        actual_model = _configured_embedding_model(self.embedding_service)
        if actual_model is not None and actual_model != self.expected_embedding_model:
            raise ValueError(
                "known-misinfo lookup requires the fact-check embedding model "
                f"{self.expected_embedding_model}, got {actual_model}"
            )

        actual_dimensions = _configured_embedding_dimensions(self.embedding_service)
        if (
            actual_dimensions is not None
            and actual_dimensions != self.expected_embedding_dimensions
        ):
            raise ValueError(
                "known-misinfo lookup requires "
                f"{self.expected_embedding_dimensions} dimensions, got {actual_dimensions}"
            )


def _to_review_date(value: datetime | None) -> date | None:
    return value.date() if value is not None else None


def _configured_embedding_model(embedding_service: Any) -> str | None:
    llm_service = getattr(embedding_service, "llm_service", None)
    embedder = getattr(llm_service, "_embedder", None)
    model = getattr(embedder, "_model", None)
    return model if isinstance(model, str) else None


def _configured_embedding_dimensions(embedding_service: Any) -> int | None:
    configured = getattr(embedding_service, "embedding_dimensions", None)
    if isinstance(configured, int):
        return configured
    llm_service = getattr(embedding_service, "llm_service", None)
    configured = getattr(llm_service, "embedding_dimensions", None)
    return configured if isinstance(configured, int) else None


def _dedupe_key(match: FactCheckMatch) -> tuple[str, str, str, str]:
    return (
        match.claim_text,
        match.publisher,
        match.review_title,
        match.review_url,
    )


async def run_known_misinfo(
    claims_report: ClaimsReport,
    *,
    lookup: KnownMisinfoLookup,
) -> list[FactCheckMatch]:
    if not claims_report.deduped_claims:
        return []

    matches: list[FactCheckMatch] = []
    seen: set[tuple[str, str, str, str]] = set()
    for claim in claims_report.deduped_claims:
        claim_text = claim.canonical_text.strip()
        if not claim_text:
            continue
        for match in await lookup.lookup(claim_text):
            key = _dedupe_key(match)
            if key in seen:
                continue
            seen.add(key)
            matches.append(match)

    return matches


__all__ = [
    "DEFAULT_KNOWN_MISINFO_LIMIT",
    "EmbeddingServiceKnownMisinfoAdapter",
    "IndexedFactCheckMatch",
    "KnownMisinfoLookup",
    "run_known_misinfo",
]
