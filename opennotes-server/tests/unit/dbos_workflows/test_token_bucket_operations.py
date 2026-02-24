from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.dbos_workflows.token_bucket.operations import (
    get_pool_status_async,
    release_tokens_async,
    try_acquire_tokens_async,
)


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_session_maker(mock_session):
    maker = MagicMock()
    maker.return_value = mock_session
    return maker


def _make_scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar.return_value = value
    return result


def _make_scalars_result(items):
    result = MagicMock()
    result.scalars.return_value = items
    return result


class TestTryAcquireTokensAsync:
    @pytest.mark.asyncio
    async def test_succeeds_when_capacity_available(self, mock_session, mock_session_maker):
        pool = MagicMock()
        pool.capacity = 10

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(None),
                _make_scalar_result(pool),
                _make_scalar_result(0),
            ]
        )

        with patch(
            "src.database.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await try_acquire_tokens_async("llm", 3, "wf-1")

        assert result is True
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fails_when_insufficient_capacity(self, mock_session, mock_session_maker):
        pool = MagicMock()
        pool.capacity = 5

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(None),
                _make_scalar_result(pool),
                _make_scalar_result(4),
            ]
        )

        with patch(
            "src.database.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await try_acquire_tokens_async("llm", 3, "wf-2")

        assert result is False
        mock_session.add.assert_not_called()
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_idempotent_when_hold_exists(self, mock_session, mock_session_maker):
        existing_hold = MagicMock()

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(existing_hold),
            ]
        )

        with patch(
            "src.database.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await try_acquire_tokens_async("llm", 3, "wf-1")

        assert result is True
        mock_session.add.assert_not_called()
        mock_session.commit.assert_not_awaited()
        assert mock_session.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_returns_false_when_pool_not_found(self, mock_session, mock_session_maker):
        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(None),
                _make_scalar_result(None),
            ]
        )

        with patch(
            "src.database.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await try_acquire_tokens_async("nonexistent", 1, "wf-3")

        assert result is False
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_succeeds_at_exact_capacity(self, mock_session, mock_session_maker):
        pool = MagicMock()
        pool.capacity = 10

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(None),
                _make_scalar_result(pool),
                _make_scalar_result(7),
            ]
        )

        with patch(
            "src.database.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await try_acquire_tokens_async("llm", 3, "wf-4")

        assert result is True
        mock_session.add.assert_called_once()


class TestReleaseTokensAsync:
    @pytest.mark.asyncio
    async def test_updates_released_at(self, mock_session, mock_session_maker):
        hold_id = uuid4()
        mock_session.execute = AsyncMock(
            return_value=_make_scalar_result(hold_id),
        )

        with patch(
            "src.database.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await release_tokens_async("llm", "wf-1")

        assert result is True
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_no_hold(self, mock_session, mock_session_maker):
        mock_session.execute = AsyncMock(
            return_value=_make_scalar_result(None),
        )

        with patch(
            "src.database.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await release_tokens_async("llm", "wf-nonexistent")

        assert result is False
        mock_session.commit.assert_awaited_once()


class TestGetPoolStatusAsync:
    @pytest.mark.asyncio
    async def test_returns_none_for_missing_pool(self, mock_session, mock_session_maker):
        mock_session.execute = AsyncMock(
            return_value=_make_scalar_result(None),
        )

        with patch(
            "src.database.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await get_pool_status_async("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_correct_info(self, mock_session, mock_session_maker):
        pool = MagicMock()
        pool.pool_name = "llm"
        pool.capacity = 10

        hold = MagicMock()
        hold.workflow_id = "wf-1"
        hold.weight = 3
        hold.acquired_at = datetime(2026, 1, 1, tzinfo=UTC)

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(pool),
                _make_scalar_result(3),
                _make_scalars_result([hold]),
            ]
        )

        with patch(
            "src.database.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await get_pool_status_async("llm")

        assert result is not None
        assert result["pool_name"] == "llm"
        assert result["capacity"] == 10
        assert result["available"] == 7
        assert result["total_held"] == 3
        assert len(result["active_holds"]) == 1
        assert result["active_holds"][0]["workflow_id"] == "wf-1"
        assert result["active_holds"][0]["weight"] == 3
