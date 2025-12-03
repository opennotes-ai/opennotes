"""Tests for AI Note Writer service."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from src.database import get_session_maker
from src.events.schemas import RequestAutoCreatedEvent
from src.fact_checking.models import FactCheckItem
from src.llm_config.models import CommunityServer
from src.llm_config.providers.base import LLMResponse
from src.llm_config.service import LLMService
from src.notes.models import Note
from src.notes.request_service import RequestService
from src.services.ai_note_writer import AINoteWriter


@pytest.fixture
async def community_server(db_session):
    """Create a test community server."""
    server = CommunityServer(
        platform="discord",
        platform_id="123456789",
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


@pytest.mark.asyncio
async def test_ai_note_writer_handles_request_auto_created_event(
    ai_note_writer, community_server, fact_check_item, db_session, mock_llm_service
):
    """Test that AINoteWriter handles REQUEST_AUTO_CREATED events correctly."""

    # Enable AI note writing for community server
    community_server.ai_note_writing_enabled = True
    db_session.add(community_server)
    await db_session.commit()

    # Create request with message archive using RequestService
    await RequestService.create_from_message(
        db=db_session,
        request_id="req_test_1",
        content="Test message that needs fact-checking",
        community_server_id=community_server.id,
        requested_by="test_user",
        platform_message_id="1234567890",
        dataset_item_id=str(fact_check_item.id),
        similarity_score=0.85,
        dataset_name="snopes",
        status="PENDING",
    )
    await db_session.commit()

    # Create event
    event = RequestAutoCreatedEvent(
        event_id="test_event_1",
        request_id="req_test_1",
        platform_message_id="12345",
        fact_check_item_id=str(fact_check_item.id),
        community_server_id=str(community_server.platform_id),
        content="Test message that needs fact-checking",
        similarity_score=0.85,
        dataset_name="snopes",
    )

    # Mock settings to enable AI note writing
    with patch("src.services.ai_note_writer.settings.AI_NOTE_WRITING_ENABLED", True):
        # Handle the event
        await ai_note_writer._handle_request_auto_created(event)

    # Verify LLM was called
    assert mock_llm_service.complete.called
    call_args = mock_llm_service.complete.call_args

    # Verify the prompt was constructed correctly
    messages = call_args[1]["messages"]
    assert len(messages) == 2
    assert messages[0].role == "system"
    assert messages[1].role == "user"
    assert "Test message that needs fact-checking" in messages[1].content
    assert "Test Fact Check" in messages[1].content

    # Verify note was created in database
    async with get_session_maker()() as session:
        result = await session.execute(select(Note).where(Note.request_id == "req_test_1"))
        note = result.scalar_one_or_none()
        assert note is not None
        assert note.ai_generated is True
        assert note.ai_provider == "openai"
        assert note.author_participant_id == "ai-note-writer"
        assert note.classification == "NOT_MISLEADING"


@pytest.mark.asyncio
async def test_ai_note_writer_respects_enabled_setting(
    ai_note_writer, community_server, fact_check_item, mock_llm_service
):
    """Test that AINoteWriter respects AI_NOTE_WRITING_ENABLED setting."""
    event = RequestAutoCreatedEvent(
        event_id="test_event_2",
        request_id="req_test_2",
        platform_message_id="12346",
        fact_check_item_id=str(fact_check_item.id),
        community_server_id=str(community_server.platform_id),
        content="Test message",
        similarity_score=0.85,
        dataset_name="snopes",
    )

    # Mock settings to disable AI note writing
    with (
        patch("src.services.ai_note_writer.settings.AI_NOTE_WRITING_ENABLED", False),
        patch.object(
            ai_note_writer, "_is_ai_note_writing_enabled", return_value=False
        ) as mock_check,
    ):
        await ai_note_writer._handle_request_auto_created(event)
        # Verify the check was performed
        assert mock_check.called

    # Verify LLM was NOT called
    assert not mock_llm_service.complete.called


@pytest.mark.asyncio
async def test_ai_note_writer_handles_rate_limiting(
    ai_note_writer, community_server, fact_check_item, db_session
):
    """Test that AINoteWriter respects rate limits."""

    # Enable AI note writing for community server
    community_server.ai_note_writing_enabled = True
    db_session.add(community_server)
    await db_session.commit()

    # Create request with message archive using RequestService
    await RequestService.create_from_message(
        db=db_session,
        request_id="req_test_3",
        content="Test message",
        community_server_id=community_server.id,
        requested_by="test_user",
        platform_message_id="1234567893",
        dataset_item_id=str(fact_check_item.id),
        similarity_score=0.85,
        dataset_name="snopes",
        status="PENDING",
    )
    await db_session.commit()

    # Create event
    event = RequestAutoCreatedEvent(
        event_id="test_event_3",
        request_id="req_test_3",
        platform_message_id="12347",
        fact_check_item_id=str(fact_check_item.id),
        community_server_id=str(community_server.platform_id),
        content="Test message",
        similarity_score=0.85,
        dataset_name="snopes",
    )

    # Mock rate limiter to return False (rate limit exceeded)
    with (
        patch("src.services.ai_note_writer.settings.AI_NOTE_WRITING_ENABLED", True),
        patch("src.services.ai_note_writer.rate_limiter") as mock_rate_limiter,
    ):
        mock_rate_limiter.check_rate_limit = AsyncMock(return_value=False)
        await ai_note_writer._handle_request_auto_created(event)

    # Verify note generation was skipped due to rate limit
    async with get_session_maker()() as session:
        result = await session.execute(select(Note).where(Note.request_id == "req_test_3"))
        note = result.scalar_one_or_none()
        assert note is None


@pytest.mark.asyncio
async def test_ai_note_writer_retries_on_failure(
    ai_note_writer, community_server, fact_check_item, mock_llm_service, db_session
):
    """Test that AINoteWriter retries on transient failures."""

    # Enable AI note writing for community server
    community_server.ai_note_writing_enabled = True
    db_session.add(community_server)
    await db_session.commit()

    # Create request with message archive using RequestService
    await RequestService.create_from_message(
        db=db_session,
        request_id="req_test_4",
        content="Test message",
        community_server_id=community_server.id,
        requested_by="test_user",
        platform_message_id="1234567894",
        dataset_item_id=str(fact_check_item.id),
        similarity_score=0.85,
        dataset_name="snopes",
        status="PENDING",
    )
    await db_session.commit()

    # Create event
    event = RequestAutoCreatedEvent(
        event_id="test_event_4",
        request_id="req_test_4",
        platform_message_id="12348",
        fact_check_item_id=str(fact_check_item.id),
        community_server_id=str(community_server.platform_id),
        content="Test message",
        similarity_score=0.85,
        dataset_name="snopes",
    )

    # Make LLM service fail twice then succeed
    mock_llm_service.complete.side_effect = [
        Exception("Transient error 1"),
        Exception("Transient error 2"),
        LLMResponse(
            content="Success after retries",
            model="gpt-5.1",
            tokens_used=100,
            finish_reason="stop",
            provider="openai",
        ),
    ]

    with patch("src.services.ai_note_writer.settings.AI_NOTE_WRITING_ENABLED", True):
        await ai_note_writer._handle_request_auto_created(event)

    # Verify LLM was called 3 times (2 failures + 1 success)
    assert mock_llm_service.complete.call_count == 3


@pytest.mark.asyncio
async def test_ai_note_writer_handles_missing_fact_check_item(
    ai_note_writer, community_server, mock_llm_service, db_session
):
    """Test that AINoteWriter handles missing fact-check items gracefully."""

    # Enable AI note writing for community server
    community_server.ai_note_writing_enabled = True
    db_session.add(community_server)
    await db_session.commit()

    # Create request with non-existent fact_check_item_id using RequestService
    await RequestService.create_from_message(
        db=db_session,
        request_id="req_test_5",
        content="Test message",
        community_server_id=community_server.id,
        requested_by="test_user",
        platform_message_id="1234567895",
        dataset_item_id="00000000-0000-0000-0000-000000099999",  # Non-existent UUID
        similarity_score=0.85,
        dataset_name="snopes",
        status="PENDING",
    )
    await db_session.commit()

    # Create event
    event = RequestAutoCreatedEvent(
        event_id="test_event_5",
        request_id="req_test_5",
        platform_message_id="12349",
        fact_check_item_id="00000000-0000-0000-0000-000000099999",  # Non-existent UUID
        community_server_id=str(community_server.platform_id),
        content="Test message",
        similarity_score=0.85,
        dataset_name="snopes",
    )

    with patch("src.services.ai_note_writer.settings.AI_NOTE_WRITING_ENABLED", True):
        # Should raise ValueError but be caught and logged
        await ai_note_writer._handle_request_auto_created(event)

    # Verify LLM was NOT called due to missing fact check item
    assert not mock_llm_service.complete.called


@pytest.mark.asyncio
async def test_ai_note_writer_handles_missing_community_server(
    ai_note_writer, fact_check_item, mock_llm_service, db_session, community_server
):
    """Test that AINoteWriter handles missing community server gracefully."""

    # Enable AI note writing for community server
    community_server.ai_note_writing_enabled = True
    db_session.add(community_server)
    await db_session.commit()

    # Create request with valid community_server but event will have fake one, using RequestService
    await RequestService.create_from_message(
        db=db_session,
        request_id="req_test_6",
        content="Test message",
        community_server_id=community_server.id,
        requested_by="test_user",
        platform_message_id="1234567896",
        dataset_item_id=str(fact_check_item.id),
        similarity_score=0.85,
        dataset_name="snopes",
        status="PENDING",
    )
    await db_session.commit()

    # Create event with non-existent community_server_id
    event = RequestAutoCreatedEvent(
        event_id="test_event_6",
        request_id="req_test_6",
        platform_message_id="12350",
        fact_check_item_id=str(fact_check_item.id),
        community_server_id="999999999",  # Non-existent server
        content="Test message",
        similarity_score=0.85,
        dataset_name="snopes",
    )

    with patch("src.services.ai_note_writer.settings.AI_NOTE_WRITING_ENABLED", True):
        # Should raise ValueError but be caught and logged
        await ai_note_writer._handle_request_auto_created(event)

    # Verify LLM was NOT called due to missing community server
    assert not mock_llm_service.complete.called


@pytest.mark.skip(
    reason="_build_prompt is an internal implementation detail that has been refactored"
)
@pytest.mark.asyncio
async def test_build_prompt_includes_all_context(ai_note_writer, fact_check_item):
    """Test that _build_prompt includes all necessary context."""
    # This tests internal implementation details that may change


@pytest.mark.asyncio
async def test_ai_note_writer_start_and_stop():
    """Test that AINoteWriter can be started and stopped."""
    mock_llm_service = MagicMock(spec=LLMService)
    ai_note_writer = AINoteWriter(llm_service=mock_llm_service)

    # Mock event subscriber
    with patch("src.services.ai_note_writer.event_subscriber") as mock_subscriber:
        mock_subscriber.subscribe = AsyncMock()

        # Start service
        await ai_note_writer.start()
        assert ai_note_writer._running is True

        # Wait for subscription task to complete (background task with retry logic)
        if ai_note_writer._subscription_task:
            await ai_note_writer._subscription_task

        assert mock_subscriber.subscribe.called

        # Stop service
        await ai_note_writer.stop()
        assert ai_note_writer._running is False


@pytest.mark.asyncio
async def test_ai_note_writer_metrics_tracking(
    ai_note_writer, community_server, fact_check_item, mock_llm_service, db_session
):
    """Test that AINoteWriter tracks metrics correctly."""

    # Enable AI note writing for community server
    community_server.ai_note_writing_enabled = True
    db_session.add(community_server)
    await db_session.commit()

    # Create request using RequestService
    await RequestService.create_from_message(
        db=db_session,
        request_id="req_test_7",
        content="Test message",
        community_server_id=community_server.id,
        requested_by="test_user",
        platform_message_id="1234567897",
        dataset_item_id=str(fact_check_item.id),
        similarity_score=0.85,
        dataset_name="snopes",
        status="PENDING",
    )
    await db_session.commit()

    # Create event
    event = RequestAutoCreatedEvent(
        event_id="test_event_7",
        request_id="req_test_7",
        platform_message_id="12351",
        fact_check_item_id=str(fact_check_item.id),
        community_server_id=str(community_server.platform_id),
        content="Test message",
        similarity_score=0.85,
        dataset_name="snopes",
    )

    with (
        patch("src.services.ai_note_writer.settings.AI_NOTE_WRITING_ENABLED", True),
        patch("src.services.ai_note_writer.ai_notes_generated_total") as mock_metric,
    ):
        await ai_note_writer._handle_request_auto_created(event)
        # Verify metric was incremented
        assert mock_metric.labels.called


@pytest.mark.skip(
    reason="_generate_note_id is an internal implementation detail that has been refactored"
)
@pytest.mark.asyncio
async def test_generate_note_id_uniqueness(ai_note_writer):
    """Test that generated note IDs are unique."""
    # This tests internal implementation details that may change


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
        assert note is not None
        assert note.ai_generated is True
        assert note.summary == "This is an AI-generated community note providing context."
        assert note.author_participant_id == "ai-note-writer"
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
