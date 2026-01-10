"""Integration tests for fact-check candidate upsert behavior.

Tests the upsert logic that handles duplicate URLs with different claims,
ensuring multi-claim articles from a single source URL are stored as
separate candidate rows.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.fact_checking.candidate_models import (
    FactCheckedItemCandidate,
    compute_claim_hash,
)
from src.fact_checking.import_pipeline.importer import upsert_candidates
from src.fact_checking.import_pipeline.schemas import NormalizedCandidate


@pytest.fixture
def multi_claim_candidates() -> list[NormalizedCandidate]:
    """Create test candidates: same URL, different claims."""
    url = "https://fullfact.org/immigration/migration-numbers"
    dataset = "fullfact.org"

    claim1 = "558,000 migrants entered the UK illegally"
    claim2 = "One million migrants arrived in 2023"

    return [
        NormalizedCandidate(
            source_url=url,
            claim_hash=compute_claim_hash(claim1),
            title="Full Fact Check: UK Migration Numbers",
            dataset_name=dataset,
            dataset_tags=["Full Fact"],
            original_id="fact-check-1",
            extracted_data={"claim": claim1},
            predicted_ratings={"false": 1.0},
        ),
        NormalizedCandidate(
            source_url=url,
            claim_hash=compute_claim_hash(claim2),
            title="Full Fact Check: UK Migration Numbers",
            dataset_name=dataset,
            dataset_tags=["Full Fact"],
            original_id="fact-check-2",
            extracted_data={"claim": claim2},
            predicted_ratings={"mostly_false": 1.0},
        ),
    ]


@pytest.fixture
def single_claim_candidate() -> NormalizedCandidate:
    """Create a single test candidate."""
    claim = "Test claim for upsert"
    return NormalizedCandidate(
        source_url="https://snopes.com/fact-check/test",
        claim_hash=compute_claim_hash(claim),
        title="Snopes Fact Check",
        dataset_name="snopes.com",
        dataset_tags=["Snopes"],
        original_id="snopes-123",
        extracted_data={"claim": claim},
        predicted_ratings={"true": 1.0},
    )


class TestCandidateUpsert:
    """Tests for candidate upsert behavior."""

    @pytest.mark.asyncio
    async def test_insert_multi_claim_candidates(
        self, db_session: AsyncSession, multi_claim_candidates: list[NormalizedCandidate]
    ) -> None:
        """Test that multiple claims with same URL are inserted as separate rows."""
        inserted, updated = await upsert_candidates(db_session, multi_claim_candidates)

        assert inserted == 2, f"Expected 2 inserts for new candidates, got {inserted}"
        assert updated == 0, f"Expected 0 updates for new candidates, got {updated}"

        query = select(FactCheckedItemCandidate).where(
            FactCheckedItemCandidate.source_url
            == "https://fullfact.org/immigration/migration-numbers"
        )
        rows = (await db_session.execute(query)).scalars().all()

        assert len(rows) == 2
        hashes = {row.claim_hash for row in rows}
        assert len(hashes) == 2

    @pytest.mark.asyncio
    async def test_upsert_same_claim_updates_existing(
        self, db_session: AsyncSession, single_claim_candidate: NormalizedCandidate
    ) -> None:
        """Test that upserting same URL+claim updates rather than duplicates."""
        inserted1, updated1 = await upsert_candidates(db_session, [single_claim_candidate])
        assert inserted1 == 1, f"Expected 1 insert for new candidate, got {inserted1}"
        assert updated1 == 0, f"Expected 0 updates for new candidate, got {updated1}"

        updated_candidate = NormalizedCandidate(
            source_url=single_claim_candidate.source_url,
            claim_hash=single_claim_candidate.claim_hash,
            title="Updated Title",
            dataset_name=single_claim_candidate.dataset_name,
            dataset_tags=single_claim_candidate.dataset_tags,
            original_id=single_claim_candidate.original_id,
            extracted_data=single_claim_candidate.extracted_data,
            predicted_ratings={"false": 0.9, "mostly_false": 0.1},
        )

        inserted2, updated2 = await upsert_candidates(db_session, [updated_candidate])
        assert inserted2 == 0, f"Expected 0 inserts for existing candidate, got {inserted2}"
        assert updated2 == 1, f"Expected 1 update for existing candidate, got {updated2}"

        query = select(FactCheckedItemCandidate).where(
            FactCheckedItemCandidate.source_url == single_claim_candidate.source_url
        )
        rows = (await db_session.execute(query)).scalars().all()
        assert len(rows) == 1

        row = rows[0]
        assert row.title == "Updated Title"
        assert row.predicted_ratings == {"false": 0.9, "mostly_false": 0.1}

    @pytest.mark.asyncio
    async def test_mixed_insert_and_update(
        self, db_session: AsyncSession, multi_claim_candidates: list[NormalizedCandidate]
    ) -> None:
        """Test upsert with mix of new and existing candidates."""
        first_only = [multi_claim_candidates[0]]
        inserted1, updated1 = await upsert_candidates(db_session, first_only)
        assert inserted1 == 1, f"Expected 1 insert for new candidate, got {inserted1}"
        assert updated1 == 0, f"Expected 0 updates for new candidate, got {updated1}"

        inserted2, updated2 = await upsert_candidates(db_session, multi_claim_candidates)
        assert inserted2 == 1, f"Expected 1 insert for new candidate, got {inserted2}"
        assert updated2 == 1, f"Expected 1 update for existing candidate, got {updated2}"

        query = select(FactCheckedItemCandidate).where(
            FactCheckedItemCandidate.source_url
            == "https://fullfact.org/immigration/migration-numbers"
        )
        rows = (await db_session.execute(query)).scalars().all()
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_different_urls_same_claim_hash(self, db_session: AsyncSession) -> None:
        """Test that same claim hash with different URLs creates separate rows.

        This is valid - same claim could be fact-checked by different sources.
        """
        claim = "Common claim text"
        claim_hash = compute_claim_hash(claim)

        candidates = [
            NormalizedCandidate(
                source_url="https://snopes.com/fact-check/common-claim",
                claim_hash=claim_hash,
                title="Snopes Check",
                dataset_name="snopes.com",
                dataset_tags=["Snopes"],
                original_id="snopes-1",
                extracted_data={"claim": claim},
            ),
            NormalizedCandidate(
                source_url="https://politifact.com/fact-check/common-claim",
                claim_hash=claim_hash,
                title="PolitiFact Check",
                dataset_name="politifact.com",
                dataset_tags=["PolitiFact"],
                original_id="politifact-1",
                extracted_data={"claim": claim},
            ),
        ]

        inserted, updated = await upsert_candidates(db_session, candidates)
        assert inserted == 2, f"Expected 2 inserts for new candidates, got {inserted}"
        assert updated == 0, f"Expected 0 updates for new candidates, got {updated}"

        query = select(FactCheckedItemCandidate).where(
            FactCheckedItemCandidate.claim_hash == claim_hash
        )
        rows = (await db_session.execute(query)).scalars().all()
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_empty_claim_hash_handling(self, db_session: AsyncSession) -> None:
        """Test that candidates with empty/None claims get consistent hashes."""
        empty_hash = compute_claim_hash("")

        candidates = [
            NormalizedCandidate(
                source_url="https://example.com/article1",
                claim_hash=empty_hash,
                title="Article 1",
                dataset_name="example.com",
                dataset_tags=["Example"],
                original_id="1",
                extracted_data={},
            ),
            NormalizedCandidate(
                source_url="https://example.com/article2",
                claim_hash=empty_hash,
                title="Article 2",
                dataset_name="example.com",
                dataset_tags=["Example"],
                original_id="2",
                extracted_data={},
            ),
        ]

        inserted, updated = await upsert_candidates(db_session, candidates)
        assert inserted == 2, f"Expected 2 inserts for new candidates, got {inserted}"
        assert updated == 0, f"Expected 0 updates for new candidates, got {updated}"

        query = select(FactCheckedItemCandidate).where(
            FactCheckedItemCandidate.claim_hash == empty_hash
        )
        rows = (await db_session.execute(query)).scalars().all()
        assert len(rows) == 2
