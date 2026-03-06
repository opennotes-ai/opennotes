from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.dbos_workflows.token_bucket.operations import (
    MAX_SCAVENGE_BATCH,
    _get_effective_capacity,
    _scavenge_zombie_holds,
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
    scalars_mock = MagicMock()
    scalars_mock.__iter__ = MagicMock(return_value=iter(items))
    scalars_mock.all.return_value = items
    result.scalars.return_value = scalars_mock
    return result


class TestGetEffectiveCapacity:
    @pytest.mark.asyncio
    async def test_returns_worker_sum_when_workers_exist(self):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_make_scalar_result(24))

        result = await _get_effective_capacity(session, "default", 12)

        assert result == 24

    @pytest.mark.asyncio
    async def test_falls_back_to_static_when_no_workers(self):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_make_scalar_result(0))

        result = await _get_effective_capacity(session, "default", 12)

        assert result == 12

    @pytest.mark.asyncio
    async def test_falls_back_to_static_when_query_returns_none(self):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_make_scalar_result(None))

        result = await _get_effective_capacity(session, "default", 10)

        assert result == 10


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
                _make_scalar_result(0),
                _make_scalar_result(4),
                _make_scalars_result([]),
            ]
        )

        with (
            patch(
                "src.database.get_session_maker",
                return_value=mock_session_maker,
            ),
            patch("src.dbos_workflows.token_bucket.operations.DBOS"),
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
                _make_scalar_result(0),
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

    @pytest.mark.asyncio
    async def test_uses_worker_capacity_when_available(self, mock_session, mock_session_maker):
        pool = MagicMock()
        pool.capacity = 10

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(None),
                _make_scalar_result(pool),
                _make_scalar_result(24),
                _make_scalar_result(0),
            ]
        )

        with patch(
            "src.database.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await try_acquire_tokens_async("llm", 20, "wf-big")

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
                _make_scalar_result(0),
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

    @pytest.mark.asyncio
    async def test_returns_worker_capacity_when_workers_exist(
        self, mock_session, mock_session_maker
    ):
        pool = MagicMock()
        pool.pool_name = "llm"
        pool.capacity = 10

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(pool),
                _make_scalar_result(24),
                _make_scalar_result(5),
                _make_scalars_result([]),
            ]
        )

        with patch(
            "src.database.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await get_pool_status_async("llm")

        assert result is not None
        assert result["capacity"] == 24
        assert result["available"] == 19


class TestActiveScavenging:
    @pytest.mark.asyncio
    async def test_scavenges_in_separate_session_when_pool_full(self):
        pool = MagicMock()
        pool.capacity = 5

        hold = MagicMock()
        hold.id = uuid4()
        hold.workflow_id = "wf-dead"
        hold.weight = 3
        hold.pool_name = "llm"

        mock_status = MagicMock()
        mock_status.status = "ERROR"

        acquire_session = AsyncMock()
        acquire_session.__aenter__ = AsyncMock(return_value=acquire_session)
        acquire_session.__aexit__ = AsyncMock(return_value=None)
        acquire_session.add = MagicMock()
        acquire_session.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(None),
                _make_scalar_result(pool),
                _make_scalar_result(0),
                _make_scalar_result(5),
            ]
        )

        scavenge_session = AsyncMock()
        scavenge_session.__aenter__ = AsyncMock(return_value=scavenge_session)
        scavenge_session.__aexit__ = AsyncMock(return_value=None)
        scavenge_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([hold]),
                MagicMock(),
            ]
        )

        sessions = iter([acquire_session, scavenge_session])
        maker = MagicMock(side_effect=lambda: next(sessions))

        call_log: list = []
        fake = _make_fake_to_thread(call_log, [mock_status])

        with (
            patch("src.database.get_session_maker", return_value=maker),
            patch(
                "src.dbos_workflows.token_bucket.operations.asyncio.to_thread",
                new=fake,
            ),
        ):
            result = await try_acquire_tokens_async("llm", 3, "wf-new")

        assert result is False
        scavenge_session.commit.assert_awaited_once()
        acquire_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_scavenging_when_capacity_available(self, mock_session, mock_session_maker):
        pool = MagicMock()
        pool.capacity = 10

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(None),
                _make_scalar_result(pool),
                _make_scalar_result(0),
                _make_scalar_result(3),
            ]
        )

        with (
            patch(
                "src.database.get_session_maker",
                return_value=mock_session_maker,
            ),
            patch("src.dbos_workflows.token_bucket.operations.DBOS") as mock_dbos,
        ):
            result = await try_acquire_tokens_async("llm", 3, "wf-new")

        assert result is True
        mock_dbos.get_workflow_status.assert_not_called()
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_scavenges_multiple_terminal_holds_in_separate_session(self):
        pool = MagicMock()
        pool.capacity = 10

        hold1 = MagicMock()
        hold1.id = uuid4()
        hold1.workflow_id = "wf-dead-1"
        hold1.weight = 4
        hold1.pool_name = "llm"

        hold2 = MagicMock()
        hold2.id = uuid4()
        hold2.workflow_id = "wf-dead-2"
        hold2.weight = 4
        hold2.pool_name = "llm"

        status_error = MagicMock()
        status_error.status = "ERROR"
        status_success = MagicMock()
        status_success.status = "SUCCESS"

        acquire_session = AsyncMock()
        acquire_session.__aenter__ = AsyncMock(return_value=acquire_session)
        acquire_session.__aexit__ = AsyncMock(return_value=None)
        acquire_session.add = MagicMock()
        acquire_session.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(None),
                _make_scalar_result(pool),
                _make_scalar_result(0),
                _make_scalar_result(10),
            ]
        )

        scavenge_session = AsyncMock()
        scavenge_session.__aenter__ = AsyncMock(return_value=scavenge_session)
        scavenge_session.__aexit__ = AsyncMock(return_value=None)
        scavenge_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([hold1, hold2]),
                MagicMock(),
                MagicMock(),
            ]
        )

        sessions = iter([acquire_session, scavenge_session])
        maker = MagicMock(side_effect=lambda: next(sessions))

        call_log: list = []
        fake = _make_fake_to_thread(call_log, [status_error, status_success])

        with (
            patch("src.database.get_session_maker", return_value=maker),
            patch(
                "src.dbos_workflows.token_bucket.operations.asyncio.to_thread",
                new=fake,
            ),
        ):
            result = await try_acquire_tokens_async("llm", 5, "wf-new")

        assert result is False
        assert len(call_log) == 2
        scavenge_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_scavenge_commit_when_nothing_scavenged(self):
        pool = MagicMock()
        pool.capacity = 5

        hold = MagicMock()
        hold.id = uuid4()
        hold.workflow_id = "wf-active"
        hold.weight = 5
        hold.pool_name = "llm"

        mock_status = MagicMock()
        mock_status.status = "PENDING"

        acquire_session = AsyncMock()
        acquire_session.__aenter__ = AsyncMock(return_value=acquire_session)
        acquire_session.__aexit__ = AsyncMock(return_value=None)
        acquire_session.add = MagicMock()
        acquire_session.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(None),
                _make_scalar_result(pool),
                _make_scalar_result(0),
                _make_scalar_result(5),
            ]
        )

        scavenge_session = AsyncMock()
        scavenge_session.__aenter__ = AsyncMock(return_value=scavenge_session)
        scavenge_session.__aexit__ = AsyncMock(return_value=None)
        scavenge_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([hold]),
            ]
        )

        sessions = iter([acquire_session, scavenge_session])
        maker = MagicMock(side_effect=lambda: next(sessions))

        call_log: list = []
        fake = _make_fake_to_thread(call_log, [mock_status])

        with (
            patch("src.database.get_session_maker", return_value=maker),
            patch(
                "src.dbos_workflows.token_bucket.operations.asyncio.to_thread",
                new=fake,
            ),
        ):
            result = await try_acquire_tokens_async("llm", 3, "wf-new")

        assert result is False
        scavenge_session.commit.assert_not_awaited()


def _make_fake_to_thread(call_log, side_effects):
    idx = 0

    async def fake_to_thread(fn, *args):
        nonlocal idx
        call_log.append((fn, args))
        effect = side_effects[idx]
        idx += 1
        if isinstance(effect, Exception):
            raise effect
        return effect

    return fake_to_thread


class TestScavengeBatchCapAndThreading:
    @pytest.mark.asyncio
    async def test_scavenge_caps_at_max_batch_size(self):
        holds = []
        for i in range(MAX_SCAVENGE_BATCH):
            h = MagicMock()
            h.id = uuid4()
            h.workflow_id = f"wf-dead-{i}"
            h.weight = 1
            h.pool_name = "llm"
            holds.append(h)

        mock_status = MagicMock()
        mock_status.status = "ERROR"

        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result(holds),
                *[MagicMock() for _ in range(MAX_SCAVENGE_BATCH)],
            ]
        )

        call_log: list[tuple[object, ...]] = []
        fake = _make_fake_to_thread(call_log, [mock_status] * MAX_SCAVENGE_BATCH)

        with patch(
            "src.dbos_workflows.token_bucket.operations.asyncio.to_thread",
            new=fake,
        ):
            released = await _scavenge_zombie_holds(session, "llm")

        assert released == MAX_SCAVENGE_BATCH
        assert len(call_log) == MAX_SCAVENGE_BATCH

    @pytest.mark.asyncio
    async def test_scavenge_uses_asyncio_to_thread(self):
        hold = MagicMock()
        hold.id = uuid4()
        hold.workflow_id = "wf-dead"
        hold.weight = 1
        hold.pool_name = "llm"

        mock_status = MagicMock()
        mock_status.status = "SUCCESS"

        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([hold]),
                MagicMock(),
            ]
        )

        call_log: list[tuple[object, ...]] = []
        fake = _make_fake_to_thread(call_log, [mock_status])

        with patch(
            "src.dbos_workflows.token_bucket.operations.asyncio.to_thread",
            new=fake,
        ):
            await _scavenge_zombie_holds(session, "llm")

        assert len(call_log) == 1

    @pytest.mark.asyncio
    async def test_scavenge_per_hold_exception_does_not_abort(self):
        hold1 = MagicMock()
        hold1.id = uuid4()
        hold1.workflow_id = "wf-explodes"
        hold1.weight = 1
        hold1.pool_name = "llm"

        hold2 = MagicMock()
        hold2.id = uuid4()
        hold2.workflow_id = "wf-dead"
        hold2.weight = 1
        hold2.pool_name = "llm"

        mock_status = MagicMock()
        mock_status.status = "ERROR"

        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([hold1, hold2]),
                MagicMock(),
            ]
        )

        call_log: list[tuple[object, ...]] = []
        fake = _make_fake_to_thread(call_log, [RuntimeError("boom"), mock_status])

        with patch(
            "src.dbos_workflows.token_bucket.operations.asyncio.to_thread",
            new=fake,
        ):
            released = await _scavenge_zombie_holds(session, "llm")

        assert released == 1


class TestGetPoolStatusClampsNegative:
    @pytest.mark.asyncio
    async def test_available_clamped_to_zero_when_overcommitted(
        self, mock_session, mock_session_maker
    ):
        pool = MagicMock()
        pool.pool_name = "llm"
        pool.capacity = 5

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(pool),
                _make_scalar_result(0),
                _make_scalar_result(10),
                _make_scalars_result([]),
            ]
        )

        with patch(
            "src.database.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await get_pool_status_async("llm")

        assert result is not None
        assert result["available"] == 0


class TestGetEffectiveCapacityFallback:
    @pytest.mark.asyncio
    async def test_falls_back_to_static_when_query_raises(self):
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=SQLAlchemyError("relation does not exist"))

        result = await _get_effective_capacity(session, "default", 12)

        assert result == 12

    @pytest.mark.asyncio
    async def test_logs_warning_on_fallback(self):
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=SQLAlchemyError("table missing"))

        with patch("src.dbos_workflows.token_bucket.operations.logger") as mock_logger:
            result = await _get_effective_capacity(session, "default", 10)

        assert result == 10
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "falling back to static capacity" in call_args[0][0]
        assert call_args[1]["extra"]["pool_name"] == "default"
        assert call_args[1]["extra"]["static_capacity"] == 10


class TestScavengeIndependentCommit:
    @pytest.mark.asyncio
    async def test_scavenged_holds_persist_when_acquisition_returns_false(self):
        pool = MagicMock()
        pool.capacity = 5

        hold = MagicMock()
        hold.id = uuid4()
        hold.workflow_id = "wf-dead"
        hold.weight = 2
        hold.pool_name = "llm"

        mock_status = MagicMock()
        mock_status.status = "ERROR"

        acquire_session = AsyncMock()
        acquire_session.__aenter__ = AsyncMock(return_value=acquire_session)
        acquire_session.__aexit__ = AsyncMock(return_value=None)
        acquire_session.add = MagicMock()
        acquire_session.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(None),
                _make_scalar_result(pool),
                _make_scalar_result(0),
                _make_scalar_result(5),
            ]
        )

        scavenge_session = AsyncMock()
        scavenge_session.__aenter__ = AsyncMock(return_value=scavenge_session)
        scavenge_session.__aexit__ = AsyncMock(return_value=None)
        scavenge_session.execute = AsyncMock(
            side_effect=[
                _make_scalars_result([hold]),
                MagicMock(),
            ]
        )

        sessions = iter([acquire_session, scavenge_session])
        maker = MagicMock(side_effect=lambda: next(sessions))

        call_log: list = []
        fake = _make_fake_to_thread(call_log, [mock_status])

        with (
            patch("src.database.get_session_maker", return_value=maker),
            patch(
                "src.dbos_workflows.token_bucket.operations.asyncio.to_thread",
                new=fake,
            ),
        ):
            result = await try_acquire_tokens_async("llm", 3, "wf-new")

        assert result is False
        scavenge_session.commit.assert_awaited_once()
        acquire_session.add.assert_not_called()


class TestScavengeCommitFailureHandled:
    @pytest.mark.asyncio
    async def test_scavenge_session_error_does_not_propagate(self):
        pool = MagicMock()
        pool.capacity = 5

        acquire_session = AsyncMock()
        acquire_session.__aenter__ = AsyncMock(return_value=acquire_session)
        acquire_session.__aexit__ = AsyncMock(return_value=None)
        acquire_session.add = MagicMock()
        acquire_session.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(None),
                _make_scalar_result(pool),
                _make_scalar_result(0),
                _make_scalar_result(5),
            ]
        )

        scavenge_session = AsyncMock()
        scavenge_session.__aenter__ = AsyncMock(return_value=scavenge_session)
        scavenge_session.__aexit__ = AsyncMock(return_value=None)
        scavenge_session.execute = AsyncMock(
            side_effect=RuntimeError("DB connection lost"),
        )

        sessions = iter([acquire_session, scavenge_session])
        maker = MagicMock(side_effect=lambda: next(sessions))

        with patch("src.database.get_session_maker", return_value=maker):
            result = await try_acquire_tokens_async("llm", 3, "wf-new")

        assert result is False


class TestCoalesceNoRedundantOr0:
    def test_operations_no_redundant_or_zero_after_coalesce(self):
        import inspect

        import src.dbos_workflows.token_bucket.operations as ops_mod

        source = inspect.getsource(ops_mod._get_effective_capacity)
        assert "scalar() or 0" not in source


class TestUniqueConstraintRace:
    @pytest.mark.asyncio
    async def test_returns_true_on_integrity_error_during_commit(
        self, mock_session, mock_session_maker
    ):
        pool = MagicMock()
        pool.capacity = 10

        mock_session.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(None),
                _make_scalar_result(pool),
                _make_scalar_result(0),
                _make_scalar_result(0),
            ]
        )
        mock_session.commit = AsyncMock(
            side_effect=IntegrityError(
                "duplicate key", params=None, orig=Exception("uq_token_hold_pool_workflow")
            )
        )

        with patch(
            "src.database.get_session_maker",
            return_value=mock_session_maker,
        ):
            result = await try_acquire_tokens_async("llm", 3, "wf-dup")

        assert result is True
