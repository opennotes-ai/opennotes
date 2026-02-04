"""Tests for DBOSClient-based enqueueing (task-1058.04).

Tests that the server uses DBOSClient for enqueueing workflows while
the worker uses DBOS.launch() for queue polling and execution.

The key architectural principle:
- Server mode: Uses DBOSClient (lightweight, enqueue only, no polling)
- Worker mode: Uses DBOS.launch() (full framework, polls and executes)
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestDbosClientFactory:
    """Tests for get_dbos_client() factory function."""

    def test_get_dbos_client_returns_client_instance(self) -> None:
        """get_dbos_client() returns a DBOSClient instance."""
        with (
            patch("src.dbos_workflows.config.DBOSClient") as mock_client_class,
            patch("src.dbos_workflows.config.settings") as mock_settings,
        ):
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            from src.dbos_workflows.config import get_dbos_client, reset_dbos_client

            reset_dbos_client()
            result = get_dbos_client()

            assert result == mock_client
            mock_client_class.assert_called_once()

    def test_get_dbos_client_returns_same_instance(self) -> None:
        """Subsequent calls return the same singleton instance."""
        with (
            patch("src.dbos_workflows.config.DBOSClient") as mock_client_class,
            patch("src.dbos_workflows.config.settings") as mock_settings,
        ):
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            from src.dbos_workflows.config import get_dbos_client, reset_dbos_client

            reset_dbos_client()
            first = get_dbos_client()
            second = get_dbos_client()

            assert first is second
            assert mock_client_class.call_count == 1

    def test_get_dbos_client_uses_sync_database_url(self) -> None:
        """Client is initialized with sync PostgreSQL URL format."""
        with (
            patch("src.dbos_workflows.config.DBOSClient") as mock_client_class,
            patch("src.dbos_workflows.config.settings") as mock_settings,
        ):
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            from src.dbos_workflows.config import get_dbos_client, reset_dbos_client

            reset_dbos_client()
            get_dbos_client()

            call_kwargs = mock_client_class.call_args.kwargs
            url = call_kwargs.get("system_database_url", "")
            assert "postgresql://" in url
            assert "postgresql+asyncpg://" not in url

    def test_reset_dbos_client_clears_instance(self) -> None:
        """reset_dbos_client() clears the cached instance."""
        with (
            patch("src.dbos_workflows.config.DBOSClient") as mock_client_class,
            patch("src.dbos_workflows.config.settings") as mock_settings,
        ):
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"
            mock_client_1 = MagicMock()
            mock_client_2 = MagicMock()
            mock_client_class.side_effect = [mock_client_1, mock_client_2]

            from src.dbos_workflows.config import get_dbos_client, reset_dbos_client

            reset_dbos_client()
            first = get_dbos_client()
            reset_dbos_client()
            second = get_dbos_client()

            assert first is not second
            assert mock_client_class.call_count == 2


class TestEnqueueWithDbosClient:
    """Tests for enqueueing via DBOSClient.enqueue()."""

    @pytest.mark.asyncio
    async def test_enqueue_single_uses_client_enqueue(self) -> None:
        """enqueue_single_fact_check_chunk uses client.enqueue() with EnqueueOptions."""
        from uuid import uuid4

        from src.dbos_workflows.rechunk_workflow import enqueue_single_fact_check_chunk

        fact_check_id = uuid4()
        community_server_id = uuid4()

        with (
            patch("src.dbos_workflows.rechunk_workflow.get_dbos_client") as mock_get_client,
        ):
            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "test-workflow-id"
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            result = await enqueue_single_fact_check_chunk(
                fact_check_id=fact_check_id,
                community_server_id=community_server_id,
            )

        assert result == "test-workflow-id"
        mock_client.enqueue.assert_called_once()
        call_args = mock_client.enqueue.call_args
        options = call_args.args[0]
        assert options["queue_name"] == "rechunk"
        assert "workflow_name" in options

    @pytest.mark.asyncio
    async def test_enqueue_options_contains_required_fields(self) -> None:
        """EnqueueOptions dict has queue_name and workflow_name."""
        from uuid import uuid4

        from src.dbos_workflows.rechunk_workflow import enqueue_single_fact_check_chunk

        fact_check_id = uuid4()

        with (
            patch("src.dbos_workflows.rechunk_workflow.get_dbos_client") as mock_get_client,
        ):
            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "test-workflow-id"
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            await enqueue_single_fact_check_chunk(
                fact_check_id=fact_check_id,
                community_server_id=None,
            )

        call_args = mock_client.enqueue.call_args
        options: dict[str, Any] = call_args.args[0]
        assert "queue_name" in options
        assert "workflow_name" in options
        assert options["queue_name"] == "rechunk"


class TestServerModeInitialization:
    """Tests for correct initialization based on SERVER_MODE.

    The key architectural principle:
    - Server mode (full): Uses DBOSClient for enqueueing only, no DBOS.launch()
    - Worker mode (dbos_worker): Uses DBOS.launch() for queue polling and execution

    This ensures only workers compete for queued workflows.
    """

    @pytest.mark.asyncio
    async def test_full_mode_uses_dbos_client(self) -> None:
        """In full mode, enqueueing uses DBOSClient (not queue.enqueue)."""
        from uuid import uuid4

        from src.dbos_workflows.rechunk_workflow import enqueue_single_fact_check_chunk

        with patch("src.dbos_workflows.rechunk_workflow.get_dbos_client") as mock_get_client:
            mock_client = MagicMock()
            mock_handle = MagicMock()
            mock_handle.workflow_id = "wf-123"
            mock_client.enqueue.return_value = mock_handle
            mock_get_client.return_value = mock_client

            await enqueue_single_fact_check_chunk(fact_check_id=uuid4())

            mock_get_client.assert_called_once()

    def test_rechunk_queue_still_defined_for_worker(self) -> None:
        """rechunk_queue is still defined for DBOS workers to poll."""
        from src.dbos_workflows.rechunk_workflow import rechunk_queue

        assert rechunk_queue.name == "rechunk"
        assert rechunk_queue.worker_concurrency == 2

    def test_dbos_client_config_uses_same_database(self) -> None:
        """DBOSClient uses the same system database as DBOS."""
        with (
            patch("src.dbos_workflows.config.DBOSClient") as mock_client_class,
            patch("src.dbos_workflows.config.DBOS") as mock_dbos_class,
            patch("src.dbos_workflows.config.settings") as mock_settings,
        ):
            mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@host/db"
            mock_settings.OTEL_SERVICE_NAME = "test-service"
            mock_settings.PROJECT_NAME = None
            mock_settings.OTLP_ENDPOINT = None
            mock_client = MagicMock()
            mock_dbos = MagicMock()
            mock_client_class.return_value = mock_client
            mock_dbos_class.return_value = mock_dbos

            from src.dbos_workflows.config import (
                get_dbos,
                get_dbos_client,
                reset_dbos,
                reset_dbos_client,
            )

            reset_dbos()
            reset_dbos_client()
            get_dbos()
            get_dbos_client()

            dbos_config = mock_dbos_class.call_args.kwargs["config"]
            client_url = mock_client_class.call_args.kwargs["system_database_url"]

            assert dbos_config["system_database_url"] == client_url
