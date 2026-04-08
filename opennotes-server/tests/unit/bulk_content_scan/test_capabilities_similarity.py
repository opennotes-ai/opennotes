"""Unit tests for the similarity search capability."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pendulum
import pytest

from src.bulk_content_scan.schemas import ContentItem, SimilarityMatch
from src.fact_checking.embedding_schemas import FactCheckMatch, SimilaritySearchResponse


def make_content_item(
    content_id: str = "msg_1",
    content_text: str = "test message about vaccines",
    community_server_id: str = "server_1",
) -> ContentItem:
    return ContentItem(
        content_id=content_id,
        platform="discord",
        content_text=content_text,
        author_id="user_1",
        author_username="testuser",
        timestamp=pendulum.now("UTC"),
        channel_id="ch_1",
        community_server_id=community_server_id,
    )


class TestSearchSimilarClaims:
    """Tests for the search_similar_claims capability function."""

    def test_function_importable(self):
        """search_similar_claims should be importable from capabilities.similarity."""
        from src.bulk_content_scan.capabilities.similarity import search_similar_claims

        assert callable(search_similar_claims)

    @pytest.mark.asyncio
    async def test_returns_similarity_match_when_match_found(self):
        """Returns SimilarityMatch when embedding service finds a match."""
        from src.bulk_content_scan.capabilities.similarity import search_similar_claims

        fact_check_id = UUID("018e8f0a-0000-7000-8000-000000000001")
        mock_match = MagicMock(spec=FactCheckMatch)
        mock_match.similarity_score = 0.85
        mock_match.content = "Vaccines cause autism"
        mock_match.title = None
        mock_match.source_url = "https://example.com/fact-check"
        mock_match.id = fact_check_id

        mock_search_response = MagicMock(spec=SimilaritySearchResponse)
        mock_search_response.matches = [mock_match]

        mock_embedding_service = AsyncMock()
        mock_embedding_service.similarity_search = AsyncMock(return_value=mock_search_response)

        mock_session = AsyncMock()

        content_item = make_content_item()
        result = await search_similar_claims(
            content_item=content_item,
            embedding_service=mock_embedding_service,
            session=mock_session,
        )

        assert result is not None
        assert isinstance(result, SimilarityMatch)
        assert result.score == 0.85
        assert result.matched_claim == "Vaccines cause autism"
        assert result.matched_source == "https://example.com/fact-check"
        assert result.fact_check_item_id == fact_check_id

    @pytest.mark.asyncio
    async def test_returns_none_when_no_matches(self):
        """Returns None when embedding service finds no matches."""
        from src.bulk_content_scan.capabilities.similarity import search_similar_claims

        mock_search_response = MagicMock(spec=SimilaritySearchResponse)
        mock_search_response.matches = []

        mock_embedding_service = AsyncMock()
        mock_embedding_service.similarity_search = AsyncMock(return_value=mock_search_response)

        mock_session = AsyncMock()

        content_item = make_content_item()
        result = await search_similar_claims(
            content_item=content_item,
            embedding_service=mock_embedding_service,
            session=mock_session,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        """Returns None when embedding service raises an exception."""
        from src.bulk_content_scan.capabilities.similarity import search_similar_claims

        mock_embedding_service = AsyncMock()
        mock_embedding_service.similarity_search = AsyncMock(side_effect=Exception("Network error"))

        mock_session = AsyncMock()

        content_item = make_content_item()
        result = await search_similar_claims(
            content_item=content_item,
            embedding_service=mock_embedding_service,
            session=mock_session,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_uses_content_text_as_query(self):
        """Passes content_item.content_text as query_text to embedding service."""
        from src.bulk_content_scan.capabilities.similarity import search_similar_claims

        mock_search_response = MagicMock(spec=SimilaritySearchResponse)
        mock_search_response.matches = []

        mock_embedding_service = AsyncMock()
        mock_embedding_service.similarity_search = AsyncMock(return_value=mock_search_response)

        mock_session = AsyncMock()

        content_item = make_content_item(content_text="specific query text")
        await search_similar_claims(
            content_item=content_item,
            embedding_service=mock_embedding_service,
            session=mock_session,
        )

        mock_embedding_service.similarity_search.assert_called_once()
        call_kwargs = mock_embedding_service.similarity_search.call_args.kwargs
        assert call_kwargs["query_text"] == "specific query text"

    @pytest.mark.asyncio
    async def test_uses_community_server_id(self):
        """Passes community_server_id to embedding service."""
        from src.bulk_content_scan.capabilities.similarity import search_similar_claims

        mock_search_response = MagicMock(spec=SimilaritySearchResponse)
        mock_search_response.matches = []

        mock_embedding_service = AsyncMock()
        mock_embedding_service.similarity_search = AsyncMock(return_value=mock_search_response)

        mock_session = AsyncMock()

        content_item = make_content_item(community_server_id="my-community-123")
        await search_similar_claims(
            content_item=content_item,
            embedding_service=mock_embedding_service,
            session=mock_session,
        )

        call_kwargs = mock_embedding_service.similarity_search.call_args.kwargs
        assert call_kwargs["community_server_id"] == "my-community-123"

    @pytest.mark.asyncio
    async def test_uses_title_when_content_is_none(self):
        """Falls back to title when match content is None."""
        from src.bulk_content_scan.capabilities.similarity import search_similar_claims

        mock_match = MagicMock(spec=FactCheckMatch)
        mock_match.similarity_score = 0.75
        mock_match.content = None
        mock_match.title = "Claim title text"
        mock_match.source_url = "https://example.com"
        mock_match.id = UUID("018e8f0a-0000-7000-8000-000000000002")

        mock_search_response = MagicMock(spec=SimilaritySearchResponse)
        mock_search_response.matches = [mock_match]

        mock_embedding_service = AsyncMock()
        mock_embedding_service.similarity_search = AsyncMock(return_value=mock_search_response)

        mock_session = AsyncMock()

        result = await search_similar_claims(
            content_item=make_content_item(),
            embedding_service=mock_embedding_service,
            session=mock_session,
        )

        assert result is not None
        assert result.matched_claim == "Claim title text"
