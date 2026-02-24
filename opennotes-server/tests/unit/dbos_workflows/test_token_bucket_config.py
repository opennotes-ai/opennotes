from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.dbos_workflows.token_bucket.config import (
    DEFAULT_POOL_CAPACITY,
    DEFAULT_POOL_NAME,
    WorkflowWeight,
    ensure_pool_exists_async,
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
