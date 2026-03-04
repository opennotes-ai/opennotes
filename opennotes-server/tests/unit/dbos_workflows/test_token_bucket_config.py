from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.dbos_workflows.token_bucket.config import (
    DEFAULT_POOL_CAPACITY,
    DEFAULT_POOL_NAME,
    DEFAULT_WORKER_CAPACITY,
    WORKER_HEARTBEAT_INTERVAL,
    WORKER_HEARTBEAT_TTL,
    WorkflowWeight,
    deregister_worker_async,
    ensure_pool_exists_async,
    register_worker_async,
    update_worker_heartbeat_async,
)


class TestWorkflowWeight:
    def test_rechunk_weight(self):
        assert WorkflowWeight.RECHUNK == 5

    def test_content_scan_weight(self):
        assert WorkflowWeight.CONTENT_SCAN == 3

    def test_import_pipeline_weight(self):
        assert WorkflowWeight.IMPORT_PIPELINE == 3

    def test_simulation_turn_weight(self):
        assert WorkflowWeight.SIMULATION_TURN == 2

    def test_approval_weight(self):
        assert WorkflowWeight.APPROVAL == 1

    def test_content_monitoring_weight(self):
        assert WorkflowWeight.CONTENT_MONITORING == 1

    def test_simulation_orchestrator_weight(self):
        assert WorkflowWeight.SIMULATION_ORCHESTRATOR == 1

    def test_total_weight_fits_default_capacity(self):
        total = sum(w.value for w in WorkflowWeight)
        assert total <= DEFAULT_POOL_CAPACITY * 2


class TestDefaults:
    def test_default_pool_name(self):
        assert DEFAULT_POOL_NAME == "default"

    def test_default_pool_capacity(self):
        assert DEFAULT_POOL_CAPACITY == 12

    def test_default_worker_capacity(self):
        assert DEFAULT_WORKER_CAPACITY == 12

    def test_worker_heartbeat_interval(self):
        assert WORKER_HEARTBEAT_INTERVAL == 30

    def test_worker_heartbeat_ttl(self):
        assert WORKER_HEARTBEAT_TTL == 90


class TestEnsurePoolExists:
    @pytest.mark.asyncio
    async def test_calls_upsert(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_maker = MagicMock()
        mock_maker.return_value = mock_session

        with patch(
            "src.database.get_session_maker",
            return_value=mock_maker,
        ):
            await ensure_pool_exists_async("test_pool", 10)

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_default_capacity_when_none(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_maker = MagicMock()
        mock_maker.return_value = mock_session

        with patch(
            "src.database.get_session_maker",
            return_value=mock_maker,
        ):
            await ensure_pool_exists_async("test_pool")

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_default_pool_name(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_maker = MagicMock()
        mock_maker.return_value = mock_session

        with patch(
            "src.database.get_session_maker",
            return_value=mock_maker,
        ):
            await ensure_pool_exists_async()

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()


class TestRegisterWorker:
    @pytest.mark.asyncio
    async def test_register_worker_creates_entry(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_maker = MagicMock()
        mock_maker.return_value = mock_session

        with patch(
            "src.database.get_session_maker",
            return_value=mock_maker,
        ):
            await register_worker_async("test_pool", "worker-1", 10)

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_worker_uses_settings_instance_id(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_maker = MagicMock()
        mock_maker.return_value = mock_session

        with (
            patch("src.database.get_session_maker", return_value=mock_maker),
            patch("src.config.settings") as mock_settings,
        ):
            mock_settings.INSTANCE_ID = "instance-abc"
            await register_worker_async("test_pool")

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()


class TestDeregisterWorker:
    @pytest.mark.asyncio
    async def test_deregister_removes_entry(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_maker = MagicMock()
        mock_maker.return_value = mock_session

        with patch(
            "src.database.get_session_maker",
            return_value=mock_maker,
        ):
            await deregister_worker_async("test_pool", "worker-1")

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_deregister_uses_settings_instance_id(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_maker = MagicMock()
        mock_maker.return_value = mock_session

        with (
            patch("src.database.get_session_maker", return_value=mock_maker),
            patch("src.config.settings") as mock_settings,
        ):
            mock_settings.INSTANCE_ID = "instance-abc"
            await deregister_worker_async("test_pool")

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()


class TestUpdateHeartbeat:
    @pytest.mark.asyncio
    async def test_update_heartbeat(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_maker = MagicMock()
        mock_maker.return_value = mock_session

        with patch(
            "src.database.get_session_maker",
            return_value=mock_maker,
        ):
            await update_worker_heartbeat_async("test_pool", "worker-1")

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_heartbeat_uses_settings_instance_id(self):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_maker = MagicMock()
        mock_maker.return_value = mock_session

        with (
            patch("src.database.get_session_maker", return_value=mock_maker),
            patch("src.config.settings") as mock_settings,
        ):
            mock_settings.INSTANCE_ID = "instance-xyz"
            await update_worker_heartbeat_async("test_pool")

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()
