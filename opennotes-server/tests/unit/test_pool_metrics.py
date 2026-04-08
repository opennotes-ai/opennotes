from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import QueuePool

from src.database import _register_pool_metrics
from src.monitoring.metrics import (
    db_pool_checked_in,
    db_pool_checked_out,
    db_pool_overflow,
    db_pool_size,
)

pytestmark = pytest.mark.unit


def _make_mock_engine(
    checkedout: int = 2, checkedin: int = 3, overflow: int = 1, size: int = 5
) -> MagicMock:
    engine = MagicMock(spec=AsyncEngine)
    pool = MagicMock(spec=QueuePool)
    pool.checkedout.return_value = checkedout
    pool.checkedin.return_value = checkedin
    pool.overflow.return_value = overflow
    pool.size.return_value = size
    engine.sync_engine.pool = pool
    return engine


class TestRegisterPoolMetrics:
    def test_registers_checkout_and_checkin_listeners(self) -> None:
        engine = _make_mock_engine()
        with patch("src.database.event") as mock_event:
            _register_pool_metrics(engine)

            calls = mock_event.listen.call_args_list
            assert len(calls) == 2
            pool = engine.sync_engine.pool
            assert calls[0][0][0] is pool
            assert calls[0][0][1] == "checkout"
            assert calls[1][0][0] is pool
            assert calls[1][0][1] == "checkin"

    def test_sets_initial_gauge_values(self) -> None:
        engine = _make_mock_engine(checkedout=0, checkedin=5, overflow=0, size=5)
        with (
            patch("src.database.event"),
            patch.object(db_pool_checked_out, "set") as mock_checked_out,
            patch.object(db_pool_checked_in, "set") as mock_checked_in,
            patch.object(db_pool_overflow, "set") as mock_overflow,
            patch.object(db_pool_size, "set") as mock_size,
        ):
            _register_pool_metrics(engine)

            mock_checked_out.assert_called_with(0)
            mock_checked_in.assert_called_with(5)
            mock_overflow.assert_called_with(0)
            mock_size.assert_called_with(5)

    def test_checkout_event_updates_gauges(self) -> None:
        engine = _make_mock_engine(checkedout=3, checkedin=2, overflow=1, size=5)
        captured_handler = None
        with patch("src.database.event") as mock_event:

            def capture_listen(pool: object, event_name: str, handler: object) -> None:
                nonlocal captured_handler
                if event_name == "checkout":
                    captured_handler = handler

            mock_event.listen.side_effect = capture_listen
            _register_pool_metrics(engine)

        assert captured_handler is not None

        with (
            patch.object(db_pool_checked_out, "set") as mock_checked_out,
            patch.object(db_pool_checked_in, "set") as mock_checked_in,
            patch.object(db_pool_overflow, "set") as mock_overflow,
            patch.object(db_pool_size, "set") as mock_size,
        ):
            captured_handler("dbapi_conn", "conn_record", "conn_proxy")

            mock_checked_out.assert_called_with(3)
            mock_checked_in.assert_called_with(2)
            mock_overflow.assert_called_with(1)
            mock_size.assert_called_with(5)

    def test_checkin_event_updates_gauges(self) -> None:
        engine = _make_mock_engine(checkedout=1, checkedin=4, overflow=0, size=5)
        captured_handler = None
        with patch("src.database.event") as mock_event:

            def capture_listen(pool: object, event_name: str, handler: object) -> None:
                nonlocal captured_handler
                if event_name == "checkin":
                    captured_handler = handler

            mock_event.listen.side_effect = capture_listen
            _register_pool_metrics(engine)

        assert captured_handler is not None

        with (
            patch.object(db_pool_checked_out, "set") as mock_checked_out,
            patch.object(db_pool_checked_in, "set") as mock_checked_in,
            patch.object(db_pool_overflow, "set") as mock_overflow,
            patch.object(db_pool_size, "set") as mock_size,
        ):
            captured_handler("dbapi_conn", "conn_record")

            mock_checked_out.assert_called_with(1)
            mock_checked_in.assert_called_with(4)
            mock_overflow.assert_called_with(0)
            mock_size.assert_called_with(5)

    def test_gauge_exception_does_not_propagate(self) -> None:
        engine = _make_mock_engine()
        captured_handler = None
        with patch("src.database.event") as mock_event:

            def capture_listen(pool: object, event_name: str, handler: object) -> None:
                nonlocal captured_handler
                if event_name == "checkout":
                    captured_handler = handler

            mock_event.listen.side_effect = capture_listen
            _register_pool_metrics(engine)

        assert captured_handler is not None

        with patch.object(db_pool_checked_out, "set", side_effect=RuntimeError("boom")):
            captured_handler("dbapi_conn", "conn_record", "conn_proxy")
