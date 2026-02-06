"""Tests for NATS handler dispatch logic in bulk content scan.

Tests the BulkScanEventHandler class: DBOS workflow dispatch, dispatch failure
handling, scan type determination based on flashpoint_detection_enabled, and
signal forwarding to the DBOS orchestrator.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.events.schemas import (
    BulkScanAllBatchesTransmittedEvent,
    BulkScanMessageBatchEvent,
)


def _make_handler():
    from src.bulk_content_scan.nats_handler import BulkScanEventHandler

    return BulkScanEventHandler(
        embedding_service=MagicMock(),
        redis_client=MagicMock(),
        nats_client=AsyncMock(),
        llm_service=MagicMock(),
    )


def _make_batch_event(
    scan_id=None,
    community_server_id=None,
    batch_number=1,
    message_count=2,
) -> BulkScanMessageBatchEvent:
    from src.bulk_content_scan.schemas import BulkScanMessage

    scan_id = scan_id or uuid4()
    community_server_id = community_server_id or uuid4()

    messages = [
        BulkScanMessage(
            message_id=f"msg_{i}",
            channel_id="ch_1",
            community_server_id="platform_123",
            content=f"test message {i}",
            author_id=f"author_{i}",
            author_username=f"user_{i}",
            timestamp="2025-01-01T00:00:00Z",
        )
        for i in range(message_count)
    ]

    return BulkScanMessageBatchEvent(
        event_id=f"evt_{uuid4().hex[:12]}",
        scan_id=scan_id,
        community_server_id=community_server_id,
        batch_number=batch_number,
        messages=messages,
    )


class TestHandleMessageBatch:
    """Tests for _handle_message_batch dispatch logic."""

    @pytest.mark.asyncio
    async def test_successful_dispatch_enqueues_batch(self) -> None:
        handler = _make_handler()
        event = _make_batch_event()

        with (
            patch(
                "src.bulk_content_scan.nats_handler.enqueue_content_scan_batch",
                new_callable=AsyncMock,
                return_value="batch-wf-123",
            ) as mock_enqueue,
            patch.object(
                handler, "_get_scan_types_for_community", new_callable=AsyncMock
            ) as mock_scan_types,
            patch(
                "src.bulk_content_scan.nats_handler.store_messages_in_redis",
                new_callable=AsyncMock,
            ),
            patch(
                "src.bulk_content_scan.nats_handler._get_batch_redis_key", return_value="test:key"
            ),
        ):
            mock_scan_types.return_value = ["similarity"]

            await handler._handle_message_batch(event)

        mock_enqueue.assert_called_once()
        call_kwargs = mock_enqueue.call_args.kwargs
        assert call_kwargs["orchestrator_workflow_id"] == str(event.scan_id)
        assert call_kwargs["scan_id"] == event.scan_id
        assert call_kwargs["batch_number"] == event.batch_number
        assert call_kwargs["messages_redis_key"] == "test:key"

    @pytest.mark.asyncio
    async def test_dispatch_failure_propagates_exception(self) -> None:
        handler = _make_handler()
        event = _make_batch_event()

        with (
            patch(
                "src.bulk_content_scan.nats_handler.enqueue_content_scan_batch",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DBOS connection refused"),
            ),
            patch.object(
                handler, "_get_scan_types_for_community", new_callable=AsyncMock
            ) as mock_scan_types,
            patch(
                "src.bulk_content_scan.nats_handler.store_messages_in_redis",
                new_callable=AsyncMock,
            ),
            patch(
                "src.bulk_content_scan.nats_handler._get_batch_redis_key", return_value="test:key"
            ),
        ):
            mock_scan_types.return_value = ["similarity"]

            with pytest.raises(RuntimeError, match="DBOS connection refused"):
                await handler._handle_message_batch(event)

    @pytest.mark.asyncio
    async def test_dispatch_passes_scan_types_from_community(self) -> None:
        handler = _make_handler()
        event = _make_batch_event()
        expected_types = ["similarity", "conversation_flashpoint"]

        with (
            patch(
                "src.bulk_content_scan.nats_handler.enqueue_content_scan_batch",
                new_callable=AsyncMock,
                return_value="wf-123",
            ) as mock_enqueue,
            patch.object(
                handler, "_get_scan_types_for_community", new_callable=AsyncMock
            ) as mock_scan_types,
            patch(
                "src.bulk_content_scan.nats_handler.store_messages_in_redis",
                new_callable=AsyncMock,
            ),
            patch(
                "src.bulk_content_scan.nats_handler._get_batch_redis_key", return_value="test:key"
            ),
        ):
            mock_scan_types.return_value = expected_types

            await handler._handle_message_batch(event)

        call_kwargs = mock_enqueue.call_args.kwargs
        assert call_kwargs["scan_types"] == expected_types

    @pytest.mark.asyncio
    async def test_dispatch_stores_messages_in_redis_before_enqueue(self) -> None:
        handler = _make_handler()
        event = _make_batch_event(message_count=3)

        with (
            patch(
                "src.bulk_content_scan.nats_handler.enqueue_content_scan_batch",
                new_callable=AsyncMock,
                return_value="wf-456",
            ) as mock_enqueue,
            patch.object(
                handler, "_get_scan_types_for_community", new_callable=AsyncMock
            ) as mock_scan_types,
            patch(
                "src.bulk_content_scan.nats_handler.store_messages_in_redis",
                new_callable=AsyncMock,
            ) as mock_store,
            patch(
                "src.bulk_content_scan.nats_handler._get_batch_redis_key",
                return_value="test:messages:key",
            ),
        ):
            mock_scan_types.return_value = ["similarity"]

            await handler._handle_message_batch(event)

        mock_store.assert_called_once()
        store_args = mock_store.call_args
        assert store_args.args[0] == handler.redis_client
        assert store_args.args[1] == "test:messages:key"
        assert len(store_args.args[2]) == 3

        call_kwargs = mock_enqueue.call_args.kwargs
        assert call_kwargs["messages_redis_key"] == "test:messages:key"


class TestHandleAllBatchesTransmitted:
    """Tests for _handle_all_batches_transmitted signal forwarding."""

    @pytest.mark.asyncio
    async def test_sends_signal_to_orchestrator(self) -> None:
        handler = _make_handler()
        scan_id = uuid4()
        event = BulkScanAllBatchesTransmittedEvent(
            event_id=f"evt_{uuid4().hex[:12]}",
            scan_id=scan_id,
            community_server_id=uuid4(),
            messages_scanned=42,
        )

        with patch(
            "src.bulk_content_scan.nats_handler.send_all_transmitted_signal",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_signal:
            await handler._handle_all_batches_transmitted(event)

        mock_signal.assert_called_once_with(
            orchestrator_workflow_id=str(scan_id),
            messages_scanned=42,
        )

    @pytest.mark.asyncio
    async def test_uses_scan_id_as_orchestrator_workflow_id(self) -> None:
        handler = _make_handler()
        scan_id = uuid4()
        event = BulkScanAllBatchesTransmittedEvent(
            event_id=f"evt_{uuid4().hex[:12]}",
            scan_id=scan_id,
            community_server_id=uuid4(),
            messages_scanned=10,
        )

        with patch(
            "src.bulk_content_scan.nats_handler.send_all_transmitted_signal",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_signal:
            await handler._handle_all_batches_transmitted(event)

        call_kwargs = mock_signal.call_args.kwargs
        assert call_kwargs["orchestrator_workflow_id"] == str(scan_id)


class TestGetScanTypesForCommunity:
    """Tests for _get_scan_types_for_community flashpoint toggle check."""

    @pytest.mark.asyncio
    async def test_includes_flashpoint_when_enabled(self) -> None:
        handler = _make_handler()
        community_server_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = True

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session_maker = MagicMock(return_value=mock_session_ctx)

        with patch(
            "src.bulk_content_scan.nats_handler.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await handler._get_scan_types_for_community(community_server_id)

        assert "conversation_flashpoint" in result

    @pytest.mark.asyncio
    async def test_excludes_flashpoint_when_disabled(self) -> None:
        handler = _make_handler()
        community_server_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = False

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session_maker = MagicMock(return_value=mock_session_ctx)

        with patch(
            "src.bulk_content_scan.nats_handler.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await handler._get_scan_types_for_community(community_server_id)

        assert "conversation_flashpoint" not in result
        assert "similarity" in result

    @pytest.mark.asyncio
    async def test_defaults_to_disabled_on_db_error(self) -> None:
        handler = _make_handler()
        community_server_id = uuid4()

        mock_session_maker = MagicMock(side_effect=RuntimeError("DB connection failed"))

        with patch(
            "src.bulk_content_scan.nats_handler.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await handler._get_scan_types_for_community(community_server_id)

        assert "conversation_flashpoint" not in result
        assert "similarity" in result

    @pytest.mark.asyncio
    async def test_excludes_flashpoint_when_server_not_found(self) -> None:
        handler = _make_handler()
        community_server_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session_maker = MagicMock(return_value=mock_session_ctx)

        with patch(
            "src.bulk_content_scan.nats_handler.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await handler._get_scan_types_for_community(community_server_id)

        assert "conversation_flashpoint" not in result
        assert "similarity" in result

    @pytest.mark.asyncio
    async def test_returns_string_scan_types(self) -> None:
        handler = _make_handler()
        community_server_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = True

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session_maker = MagicMock(return_value=mock_session_ctx)

        with patch(
            "src.bulk_content_scan.nats_handler.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await handler._get_scan_types_for_community(community_server_id)

        assert all(isinstance(st, str) for st in result)


class TestRegister:
    """Tests for handler registration."""

    def test_registers_both_event_handlers(self) -> None:
        handler = _make_handler()

        with patch.object(handler.subscriber, "register_handler") as mock_register:
            handler.register()

        assert mock_register.call_count == 2
        registered_types = {call.args[0] for call in mock_register.call_args_list}
        from src.events.schemas import EventType

        assert EventType.BULK_SCAN_MESSAGE_BATCH in registered_types
        assert EventType.BULK_SCAN_ALL_BATCHES_TRANSMITTED in registered_types
