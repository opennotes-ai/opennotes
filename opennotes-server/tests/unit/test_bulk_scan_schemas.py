"""Tests for bulk content scan schemas."""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from src.bulk_content_scan.schemas import BulkScanMessage, SimilarityMatch
from src.bulk_content_scan.service import BulkContentScanService
from src.fact_checking.embedding_schemas import FactCheckMatch


class TestSimilarityMatch:
    """Tests for SimilarityMatch schema."""

    def test_similarity_match_requires_fact_check_item_id(self) -> None:
        """SimilarityMatch should include fact_check_item_id field."""
        fact_check_id = uuid4()

        match = SimilarityMatch(
            score=0.85,
            matched_claim="This claim has been debunked",
            matched_source="https://factcheck.org/article/123",
            fact_check_item_id=fact_check_id,
        )

        assert match.fact_check_item_id == fact_check_id
        assert match.scan_type == "similarity"
        assert match.score == 0.85

    def test_similarity_match_fact_check_item_id_in_serialization(self) -> None:
        """fact_check_item_id should be included in model serialization."""
        fact_check_id = uuid4()

        match = SimilarityMatch(
            score=0.75,
            matched_claim="Test claim",
            matched_source="https://example.com",
            fact_check_item_id=fact_check_id,
        )

        data = match.model_dump()
        assert "fact_check_item_id" in data
        assert data["fact_check_item_id"] == fact_check_id


class TestBuildFlaggedMessage:
    """Tests for _build_flagged_message method."""

    def test_build_flagged_message_passes_fact_check_item_id(self) -> None:
        """_build_flagged_message should pass FactCheckMatch.id as fact_check_item_id."""
        fact_check_id = uuid4()
        mock_session = MagicMock()
        mock_embedding_service = MagicMock()
        mock_redis = MagicMock()

        service = BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
        )

        message = BulkScanMessage(
            message_id="123456789",
            channel_id="987654321",
            community_server_id="111222333",
            content="This is a test message",
            author_id="444555666",
            timestamp=datetime.now(UTC),
        )

        fact_check_match = FactCheckMatch(
            id=fact_check_id,
            dataset_name="snopes",
            dataset_tags=["politics"],
            title="Fact Check Title",
            content="This claim is false",
            summary="Debunked claim",
            rating="false",
            source_url="https://snopes.com/fact-check/123",
            published_date=datetime.now(UTC),
            author="John Doe",
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            similarity_score=0.92,
        )

        flagged = service._build_flagged_message(message, fact_check_match)

        assert len(flagged.matches) == 1
        match = flagged.matches[0]
        assert match.fact_check_item_id == fact_check_id
        assert match.score == 0.92
        assert match.matched_claim == "This claim is false"
        assert match.matched_source == "https://snopes.com/fact-check/123"
