"""Tests for AI Note Writer service (on-demand generate_note_for_request)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.fact_checking.models import FactCheckItem
from src.llm_config.models import CommunityServer
from src.llm_config.providers.base import LLMResponse
from src.llm_config.service import LLMService
from src.notes.request_service import RequestService
from src.services.ai_note_writer import AINoteWriter


@pytest.fixture
async def community_server(db_session):
    """Create a test community server."""
    server = CommunityServer(
        platform="discord",
        platform_community_server_id="123456789",
        name="Test Server",
    )
    db_session.add(server)
    await db_session.commit()
    await db_session.refresh(server)
    return server


@pytest.fixture
def ai_note_writing_enabled():
    """Fixture to enable AI note writing for tests (mocks the settings flag)."""
    with patch("src.services.ai_note_writer.settings.AI_NOTE_WRITING_ENABLED", True):
        yield


@pytest.fixture
async def fact_check_item(db_session):
    """Create a test fact-check item."""
    item = FactCheckItem(
        dataset_name="snopes",
        dataset_tags=["test", "fact-check"],
        title="Test Fact Check",
        content="This is a test fact check item with detailed information.",
        summary="Test fact check summary",
        rating="False",
        source_url="https://example.com/fact-check",
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


@pytest.fixture
def mock_llm_service():
    """Create a mock LLM service."""
    service = MagicMock(spec=LLMService)
    service.complete = AsyncMock(
        return_value=LLMResponse(
            content="This is an AI-generated community note providing context.",
            model="gpt-5.1",
            tokens_used=150,
            finish_reason="stop",
            provider="openai",
        )
    )
    return service


@pytest.fixture
def ai_note_writer(mock_llm_service):
    """Create an AI Note Writer instance with mocked LLM service."""
    return AINoteWriter(llm_service=mock_llm_service)


# Tests for generate_note_for_request (on-demand AI note generation)


@pytest.fixture
async def test_request(db_session, community_server, fact_check_item):
    """Create a test request with fact-check metadata."""
    # Create request using RequestService
    request = await RequestService.create_from_message(
        db=db_session,
        request_id="discord-test-request-1",
        content="I heard that hitler invented the inflatable sex doll",
        community_server_id=community_server.id,
        requested_by="test_user",
        platform_message_id="1234567890",
        platform_channel_id="9876543210",
        platform_author_id="1111111111",
        dataset_item_id=str(fact_check_item.id),  # UUID as string
        similarity_score=0.85,
        dataset_name="snopes",
        status="PENDING",
    )
    await db_session.commit()
    await db_session.refresh(request)
    return request


@pytest.mark.asyncio
async def test_generate_note_for_request_success(
    ai_note_writer, test_request, db_session, mock_llm_service, ai_note_writing_enabled
):
    """Test successful on-demand AI note generation."""
    # Mock rate limiter to allow request
    with patch("src.services.ai_note_writer.rate_limiter") as mock_rate_limiter:
        mock_rate_limiter.check_rate_limit = AsyncMock(return_value=(True, 9))

        # Generate note
        note = await ai_note_writer.generate_note_for_request(db_session, test_request.request_id)

        # Verify rate limiter was called correctly
        mock_rate_limiter.check_rate_limit.assert_called_once()
        call_kwargs = mock_rate_limiter.check_rate_limit.call_args.kwargs
        assert "community_server_id" in call_kwargs

        # Verify note was created
        from src.users import PLACEHOLDER_USER_ID

        assert note is not None
        assert note.ai_generated is True
        assert note.summary == "This is an AI-generated community note providing context."
        assert note.author_id == PLACEHOLDER_USER_ID
        assert note.classification == "NOT_MISLEADING"

        # Verify LLM service was called
        assert mock_llm_service.complete.called


@pytest.mark.asyncio
async def test_generate_note_for_request_rate_limiter_tuple_return(
    ai_note_writer, test_request, db_session, ai_note_writing_enabled
):
    """Test that rate limiter returns tuple (allowed, remaining) correctly."""
    with patch("src.services.ai_note_writer.rate_limiter") as mock_rate_limiter:
        # Rate limiter should return tuple
        mock_rate_limiter.check_rate_limit = AsyncMock(return_value=(False, 0))

        # Should raise ValueError due to rate limit
        with pytest.raises(ValueError, match="Rate limit exceeded"):
            await ai_note_writer.generate_note_for_request(db_session, test_request.request_id)

        # Verify the return value was properly unpacked
        assert mock_rate_limiter.check_rate_limit.called


@pytest.mark.asyncio
async def test_generate_note_for_request_uuid_type_handling(
    ai_note_writer, test_request, db_session, mock_llm_service, ai_note_writing_enabled
):
    """Test that dataset_item_id (UUID string) is correctly converted to UUID object."""
    # Ensure dataset_item_id is a string UUID
    assert isinstance(test_request.dataset_item_id, str)
    # Verify it's a valid UUID string
    UUID(test_request.dataset_item_id)

    with patch("src.services.ai_note_writer.rate_limiter") as mock_rate_limiter:
        mock_rate_limiter.check_rate_limit = AsyncMock(return_value=(True, 9))

        # This should NOT raise "invalid literal for int()" error
        note = await ai_note_writer.generate_note_for_request(db_session, test_request.request_id)

        assert note is not None
        # Fact check item lookup succeeded with UUID conversion


@pytest.mark.asyncio
async def test_generate_note_for_request_llm_response_tokens_used(
    ai_note_writer, test_request, db_session, ai_note_writing_enabled
):
    """Test that LLMResponse.tokens_used is accessed correctly (not .usage)."""
    mock_llm_service = MagicMock(spec=LLMService)
    # Create response with tokens_used attribute (not usage)
    mock_llm_service.complete = AsyncMock(
        return_value=LLMResponse(
            content="Test note content",
            model="gpt-5.1",
            tokens_used=250,
            finish_reason="stop",
            provider="openai",
        )
    )
    ai_note_writer.llm_service = mock_llm_service

    with patch("src.services.ai_note_writer.rate_limiter") as mock_rate_limiter:
        mock_rate_limiter.check_rate_limit = AsyncMock(return_value=(True, 9))

        # This should NOT raise AttributeError about .usage
        note = await ai_note_writer.generate_note_for_request(db_session, test_request.request_id)

        assert note is not None
        assert mock_llm_service.complete.called


@pytest.mark.skip(
    reason="AI note writer now supports multiple strategies and doesn't require fact-check data"
)
@pytest.mark.asyncio
async def test_generate_note_for_request_missing_fact_check_data(
    ai_note_writer, db_session, community_server
):
    """Test that missing fact-check metadata is handled gracefully."""
    # AI note writer now uses a "general_explanation" strategy when fact-check data is missing


@pytest.mark.skip(
    reason="AI note writer behavior has changed - check configuration handling in implementation"
)
@pytest.mark.asyncio
async def test_generate_note_for_request_disabled_for_server(
    ai_note_writer, test_request, db_session, community_server
):
    """Test that AI note writing respects community server configuration."""
    # Implementation may have changed how it handles disabled servers


@pytest.mark.asyncio
async def test_generate_note_for_request_nonexistent_request(ai_note_writer, db_session):
    """Test that error is raised for non-existent request."""
    with pytest.raises(ValueError, match="Request not found"):
        await ai_note_writer.generate_note_for_request(db_session, "nonexistent-request-id")


@pytest.mark.asyncio
async def test_generate_note_for_request_invalid_fact_check_item_id(
    ai_note_writer, db_session, community_server, ai_note_writing_enabled
):
    """Test that error is raised when fact-check item doesn't exist."""
    # Create request with non-existent fact-check item ID using RequestService
    fake_uuid = str(uuid4())
    request = await RequestService.create_from_message(
        db=db_session,
        request_id="discord-test-invalid-fact-check",
        content="Test message",
        community_server_id=community_server.id,
        requested_by="test_user",
        platform_message_id="1234567890",
        dataset_item_id=fake_uuid,
        similarity_score=0.85,
        dataset_name="snopes",
        status="PENDING",
    )
    await db_session.commit()

    with patch("src.services.ai_note_writer.rate_limiter") as mock_rate_limiter:
        mock_rate_limiter.check_rate_limit = AsyncMock(return_value=(True, 9))

        with pytest.raises(ValueError, match="Fact-check item not found"):
            await ai_note_writer.generate_note_for_request(db_session, request.request_id)
