from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.url_content_scan.claims_schemas import ClaimsReport, DedupedClaim


@pytest.mark.asyncio
async def test_run_known_misinfo_maps_existing_fact_check_index_matches() -> None:
    from src.fact_checking.embedding_schemas import FactCheckMatch as IndexMatch
    from src.fact_checking.embedding_schemas import SimilaritySearchResponse
    from src.url_content_scan.analyses.claims.known_misinfo import (
        EmbeddingServiceKnownMisinfoAdapter,
        run_known_misinfo,
    )

    class _FakeEmbeddingService:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def similarity_search(self, **kwargs):
            self.calls.append(kwargs)
            return SimilaritySearchResponse(
                matches=[
                    IndexMatch(
                        id=uuid4(),
                        dataset_name="snopes",
                        dataset_tags=["Snopes"],
                        title="No, vaccines do not cause autism",
                        content="Longer fact-check body",
                        summary="Debunked",
                        rating="False",
                        source_url="https://www.snopes.com/fact-check/vaccines-autism/",
                        published_date=datetime(2024, 1, 5, tzinfo=UTC),
                        author="Snopes",
                        embedding_provider="openai",
                        embedding_model="text-embedding-3-small",
                        similarity_score=0.91,
                        cosine_similarity=0.93,
                    )
                ],
                query_text=kwargs["query_text"],
                dataset_tags=[],
                similarity_threshold=0.85,
                score_threshold=0.1,
                total_matches=1,
            )

    claims_report = ClaimsReport(
        deduped_claims=[
            DedupedClaim(
                canonical_text="Vaccines cause autism.",
                occurrence_count=2,
                author_count=2,
                utterance_ids=["u-1", "u-2"],
                representative_authors=["alice", "bob"],
            )
        ],
        total_claims=2,
        total_unique=1,
    )
    fake_service = _FakeEmbeddingService()
    adapter = EmbeddingServiceKnownMisinfoAdapter(
        embedding_service=fake_service,
        db=object(),
        community_server_id="url-scan",
    )

    matches = await run_known_misinfo(claims_report, lookup=adapter)

    assert len(matches) == 1
    assert matches[0].claim_text == "Vaccines cause autism."
    assert matches[0].publisher == "Snopes"
    assert matches[0].review_title == "No, vaccines do not cause autism"
    assert matches[0].review_url == "https://www.snopes.com/fact-check/vaccines-autism/"
    assert matches[0].textual_rating == "False"
    assert matches[0].review_date is not None
    assert fake_service.calls[0]["query_text"] == "Vaccines cause autism."
    assert fake_service.calls[0]["dataset_tags"] == []
