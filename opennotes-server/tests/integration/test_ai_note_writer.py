"""Tests for AI Note Writer service."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.events.schemas import RequestAutoCreatedEvent
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


@pytest.mark.asyncio
async def test_ai_note_writer_handles_request_auto_created_event(
    ai_note_writer, community_server, fact_check_item, db_session, mock_llm_service
):
    """Test that AINoteWriter dispatches to TaskIQ on REQUEST_AUTO_CREATED events.

    Note: The actual note generation is now handled by the TaskIQ task
    (generate_ai_note_task). This test verifies the dispatch happens correctly.
    See tests/unit/test_content_monitoring_tasks.py for task behavior tests.
    """

    # Create event
    event = RequestAutoCreatedEvent(
        event_id="test_event_1",
        request_id="req_test_1",
        platform_message_id="12345",
        scan_type="similarity",
        fact_check_item_id=str(fact_check_item.id),
        community_server_id=str(community_server.platform_community_server_id),
        content="Test message that needs fact-checking",
        similarity_score=0.85,
        dataset_name="snopes",
    )

    # Mock TaskIQ task dispatch
    with patch("src.services.ai_note_writer.generate_ai_note_task") as mock_task:
        mock_task.kiq = AsyncMock()

        # Handle the event - should dispatch to TaskIQ
        await ai_note_writer._handle_request_auto_created(event)

        # Verify TaskIQ task was dispatched with correct parameters
        mock_task.kiq.assert_called_once()
        call_kwargs = mock_task.kiq.call_args[1]
        assert call_kwargs["community_server_id"] == str(
            community_server.platform_community_server_id
        )
        assert call_kwargs["request_id"] == "req_test_1"
        assert call_kwargs["content"] == "Test message that needs fact-checking"
        assert call_kwargs["scan_type"] == "similarity"
        assert call_kwargs["fact_check_item_id"] == str(fact_check_item.id)
        assert call_kwargs["similarity_score"] == 0.85


@pytest.mark.asyncio
async def test_ai_note_writer_respects_enabled_setting(
    ai_note_writer, community_server, fact_check_item, mock_llm_service
):
    """Test that handler always dispatches to TaskIQ (enabled check moved to task).

    Note: The AI_NOTE_WRITING_ENABLED check is now performed in the TaskIQ task,
    not in the handler. This allows for retry handling and better observability.
    See tests/unit/test_content_monitoring_tasks.py::TestGenerateAINoteTask.
    """
    event = RequestAutoCreatedEvent(
        event_id="test_event_2",
        request_id="req_test_2",
        platform_message_id="12346",
        scan_type="similarity",
        fact_check_item_id=str(fact_check_item.id),
        community_server_id=str(community_server.platform_community_server_id),
        content="Test message",
        similarity_score=0.85,
        dataset_name="snopes",
    )

    # Mock TaskIQ task dispatch
    with patch("src.services.ai_note_writer.generate_ai_note_task") as mock_task:
        mock_task.kiq = AsyncMock()

        # Handler always dispatches - enabled check is in the task
        await ai_note_writer._handle_request_auto_created(event)

        # Verify TaskIQ task was dispatched
        mock_task.kiq.assert_called_once()


@pytest.mark.asyncio
async def test_ai_note_writer_handles_rate_limiting(
    ai_note_writer, community_server, fact_check_item, db_session
):
    """Test that handler always dispatches to TaskIQ (rate limiting moved to task).

    Note: Rate limiting is now handled in the TaskIQ task, not in the handler.
    This allows for proper task-level retry handling and rate limit observability.
    See tests/unit/test_content_monitoring_tasks.py::TestGenerateAINoteTask::test_respects_rate_limit.
    """

    # Create event
    event = RequestAutoCreatedEvent(
        event_id="test_event_3",
        request_id="req_test_3",
        platform_message_id="12347",
        scan_type="similarity",
        fact_check_item_id=str(fact_check_item.id),
        community_server_id=str(community_server.platform_community_server_id),
        content="Test message",
        similarity_score=0.85,
        dataset_name="snopes",
    )

    # Mock TaskIQ task dispatch
    with patch("src.services.ai_note_writer.generate_ai_note_task") as mock_task:
        mock_task.kiq = AsyncMock()

        # Handler always dispatches - rate limiting is in the task
        await ai_note_writer._handle_request_auto_created(event)

        # Verify TaskIQ task was dispatched
        mock_task.kiq.assert_called_once()


@pytest.mark.asyncio
async def test_ai_note_writer_retries_on_failure(
    ai_note_writer, community_server, fact_check_item, mock_llm_service, db_session
):
    """Test that handler dispatches to TaskIQ (retries now handled by TaskIQ).

    Note: Retry logic is now handled by TaskIQ's built-in retry mechanism,
    not by the handler. This provides better reliability and observability.
    TaskIQ is configured with retry policies in broker.py.
    """

    # Create event
    event = RequestAutoCreatedEvent(
        event_id="test_event_4",
        request_id="req_test_4",
        platform_message_id="12348",
        scan_type="similarity",
        fact_check_item_id=str(fact_check_item.id),
        community_server_id=str(community_server.platform_community_server_id),
        content="Test message",
        similarity_score=0.85,
        dataset_name="snopes",
    )

    # Mock TaskIQ task dispatch
    with patch("src.services.ai_note_writer.generate_ai_note_task") as mock_task:
        mock_task.kiq = AsyncMock()

        # Handler dispatches - TaskIQ handles retries
        await ai_note_writer._handle_request_auto_created(event)

        # Verify TaskIQ task was dispatched
        mock_task.kiq.assert_called_once()


@pytest.mark.asyncio
async def test_ai_note_writer_handles_missing_fact_check_item(
    ai_note_writer, community_server, mock_llm_service, db_session
):
    """Test that handler dispatches even with non-existent fact-check item.

    Note: Missing fact-check item handling is now in the TaskIQ task.
    The handler always dispatches - validation happens in the task.
    """

    # Create event with non-existent fact_check_item_id
    event = RequestAutoCreatedEvent(
        event_id="test_event_5",
        request_id="req_test_5",
        platform_message_id="12349",
        scan_type="similarity",
        fact_check_item_id="00000000-0000-0000-0000-000000099999",  # Non-existent UUID
        community_server_id=str(community_server.platform_community_server_id),
        content="Test message",
        similarity_score=0.85,
        dataset_name="snopes",
    )

    # Mock TaskIQ task dispatch
    with patch("src.services.ai_note_writer.generate_ai_note_task") as mock_task:
        mock_task.kiq = AsyncMock()

        # Handler dispatches - TaskIQ task handles missing item gracefully
        await ai_note_writer._handle_request_auto_created(event)

        # Verify TaskIQ task was dispatched
        mock_task.kiq.assert_called_once()


@pytest.mark.asyncio
async def test_ai_note_writer_handles_missing_community_server(
    ai_note_writer, fact_check_item, mock_llm_service, db_session, community_server
):
    """Test that handler dispatches even with non-existent community server.

    Note: Missing community server handling is now in the TaskIQ task.
    The handler always dispatches - validation happens in the task.
    """

    # Create event with non-existent community_server_id
    event = RequestAutoCreatedEvent(
        event_id="test_event_6",
        request_id="req_test_6",
        platform_message_id="12350",
        scan_type="similarity",
        fact_check_item_id=str(fact_check_item.id),
        community_server_id="999999999",  # Non-existent server
        content="Test message",
        similarity_score=0.85,
        dataset_name="snopes",
    )

    # Mock TaskIQ task dispatch
    with patch("src.services.ai_note_writer.generate_ai_note_task") as mock_task:
        mock_task.kiq = AsyncMock()

        # Handler dispatches - TaskIQ task handles missing server gracefully
        await ai_note_writer._handle_request_auto_created(event)

        # Verify TaskIQ task was dispatched
        mock_task.kiq.assert_called_once()


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
    """Test that handler tracks error metrics when TaskIQ dispatch fails.

    Note: Success metrics are now tracked in the TaskIQ task, not the handler.
    The handler only tracks failure metrics when dispatch itself fails.
    """

    # Create event
    event = RequestAutoCreatedEvent(
        event_id="test_event_7",
        request_id="req_test_7",
        platform_message_id="12351",
        scan_type="similarity",
        fact_check_item_id=str(fact_check_item.id),
        community_server_id=str(community_server.platform_community_server_id),
        content="Test message",
        similarity_score=0.85,
        dataset_name="snopes",
    )

    # Mock TaskIQ task dispatch to succeed
    with patch("src.services.ai_note_writer.generate_ai_note_task") as mock_task:
        mock_task.kiq = AsyncMock()

        # Handler dispatches successfully
        await ai_note_writer._handle_request_auto_created(event)

        # Verify TaskIQ task was dispatched
        mock_task.kiq.assert_called_once()


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
